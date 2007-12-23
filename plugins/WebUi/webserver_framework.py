#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# webserver_framework.py
#
# Copyright (C) Martijn Voncken 2007 <mvoncken@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, write to:
#     The Free Software Foundation, Inc.,
#     51 Franklin Street, Fifth Floor
#     Boston, MA  02110-1301, USA.
#
#  In addition, as a special exception, the copyright holders give
#  permission to link the code of portions of this program with the OpenSSL
#  library.
#  You must obey the GNU General Public License in all respects for all of
#  the code used other than OpenSSL. If you modify file(s) with this
#  exception, you may extend this exception to your version of the file(s),
#  but you are not obligated to do so. If you do not wish to do so, delete
#  this exception statement from your version. If you delete this exception
#  statement from all source files in the program, then also delete it here.

"""
Todo's before stable:
-__init__:kill->restart is not waiting for kill to be finished.
--later/features:---
-alternating rows?
-set prio
-clear finished?
-torrent files.
"""
import lib.webpy022 as web

from lib.webpy022.webapi import cookies, setcookie as w_setcookie
from lib.webpy022.http import seeother, url
from lib.webpy022 import template,changequery as self_url
from lib.webpy022.utils import Storage
from lib.static_handler import static_handler

from deluge.common import fsize,fspeed

import traceback
import random
from operator import attrgetter
import datetime
import pickle
from md5 import md5
from urlparse import urlparse

from deluge import common
from webserver_common import  REVNO, VERSION, log
import webserver_common as ws
from debugerror import deluge_debugerror

#init:
web.webapi.internalerror = deluge_debugerror
#/init
debug_unicode = False
#methods:
def setcookie(key, val):
    """add 30 days expires header for persistent cookies"""
    return w_setcookie(key, val , expires=2592000)

#really simple sessions, to bad i had to implement them myself.
def start_session():
    log.debug('start session')
    session_id = str(random.random())
    ws.SESSIONS.append(session_id)
    #if len(ws.SESSIONS) > 20:  #save max 20 sessions?
    #    ws.SESSIONS = ws.SESSIONS[-20:]
    #not thread safe! , but a verry rare bug.
    #f = open(ws.session_file,'wb')
    #pickle.dump(ws.SESSIONS, f)
    #f.close()
    setcookie("session_id", session_id)

def end_session():
    session_id = getcookie("session_id")
    #if session_id in ws.SESSIONS:
    #    ws.SESSIONS.remove(session_id)
        #not thread safe! , but a verry rare bug.
        #f = open(ws.session_file,'wb')
        #pickle.dump(ws.SESSIONS, f)
        #f.close()
    setcookie("session_id","")

def do_redirect():
    """for redirects after a POST"""
    vars = web.input(redir = None)
    ck = cookies()
    url_vars = {}

    if vars.redir:
        seeother(vars.redir)
        return
    #todo:cleanup
    if ("order" in ck and "sort" in ck):
        url_vars.update({'sort':ck['sort'] ,'order':ck['order'] })
    if ("filter" in ck) and ck['filter']:
        url_vars['filter'] = ck['filter']
    if ("category" in ck) and ck['category']:
        url_vars['category'] = ck['category']

    seeother(url("/index", **url_vars))

def error_page(error):
    web.header("Content-Type", "text/html; charset=utf-8")
    web.header("Cache-Control", "no-cache, must-revalidate")
    print ws.render.error(error)

def getcookie(key, default = None):
    key = str(key).strip()
    ck = cookies()
    return ck.get(key, default)

#deco's:
def deluge_page_noauth(func):
    """
    add http headers
    print result of func
    """
    def deco(self, name = None):
            web.header("Content-Type", "text/html; charset=utf-8")
            web.header("Cache-Control", "no-cache, must-revalidate")
            res = func(self, name)
            print res
    deco.__name__ = func.__name__
    return deco

def check_session(func):
    """
    a decorator
    return func if session is valid, else redirect to login page.
    """
    def deco(self, name = None):
        log.debug('%s.%s(name=%s)'  % (self.__class__.__name__, func.__name__,
            name))
        vars = web.input(redir_after_login = None)
        ck = cookies()
        if ck.has_key("session_id") and ck["session_id"] in ws.SESSIONS:
            return func(self, name) #ok, continue..
        elif vars.redir_after_login:
            seeother(url("/login",redir=self_url()))
        else:
            seeother("/login") #do not continue, and redirect to login page
    return deco

def deluge_page(func):
    return check_session(deluge_page_noauth(func))

#combi-deco's:
def auto_refreshed(func):
    "decorator:adds a refresh header"
    def deco(self, name = None):
        if getcookie('auto_refresh') == '1':
            web.header("Refresh", "%i ; url=%s" %
                (int(getcookie('auto_refresh_secs',10)),self_url()))
        return func(self, name)
    deco.__name__ = func.__name__
    return deco

def remote(func):
    "decorator for remote api's"
    def deco(self, name = None):
        try:
            log.debug('%s.%s(%s)' ,self.__class__.__name__, func.__name__,name )
            print func(self, name)
        except Exception, e:
            print 'error:%s' % e.message
            print '-'*20
            print  traceback.format_exc()
    deco.__name__ = func.__name__
    return deco

#utils:
def check_pwd(pwd):
    m = md5()
    m.update(ws.config.get('pwd_salt'))
    m.update(pwd)
    return (m.digest() == ws.config.get('pwd_md5'))

def get_stats():
    stats = Storage({
    'download_rate':fspeed(ws.proxy.get_download_rate()),
    'upload_rate':fspeed(ws.proxy.get_upload_rate()),
    'max_download':ws.proxy.get_config_value('max_download_speed_bps'),
    'max_upload':ws.proxy.get_config_value('max_upload_speed_bps'),
    'num_connections':ws.proxy.get_num_connections(),
    'max_num_connections':ws.proxy.get_config_value('max_connections_global')
    })
    if stats.max_upload < 0:
        stats.max_upload = _("Unlimited")
    else:
        stats.max_upload = fspeed(stats.max_upload)

    if stats.max_download < 0:
        stats.max_download = _("Unlimited")
    else:
        stats.max_download = fspeed(stats.max_download)

    return stats


def get_torrent_status(torrent_id):
    """
    helper method.
    enhance ws.proxy.get_torrent_status with some extra data
    """
    status = Storage(ws.proxy.get_torrent_status(torrent_id,ws.TORRENT_KEYS))

    #add missing values for deluge 0.6:
    for key in ws.TORRENT_KEYS:
        if not key in status:
            status[key] = 0

    status["id"] = torrent_id

    url = urlparse(status.tracker)
    if hasattr(url,'hostname'):
        status.category = url.hostname or 'unknown'
    else:
        status.category = 'No-tracker'

    #0.5-->0.6
    status.download_rate = status.download_payload_rate
    status.upload_rate = status.upload_payload_rate

    #for naming the status-images
    status.calc_state_str = "downloading"
    if status.paused:
        status.calc_state_str= "inactive"
    elif status.is_seed:
        status.calc_state_str = "seeding"

    #action for torrent_pause
    if status.user_paused:
        status.action = "start"
    else:
        status.action = "stop"

    if status.user_paused:
        status.message = _("Paused")
    elif status.paused:
        status.message = _("Queued")
    else:
        status.message = (ws.STATE_MESSAGES[status.state])

    #add some pre-calculated values
    status.update({
        "calc_total_downloaded"  : (fsize(status.total_done)
            + " (" + fsize(status.total_download) + ")"),
        "calc_total_uploaded": (fsize(status.uploaded_memory
            + status.total_payload_upload) + " ("
            + fsize(status.total_upload) + ")"),
    })

    #no non-unicode string may enter the templates.
    #FIXED,l was a translation bug..
    if debug_unicode:
        for k, v in status.iteritems():
            if (not isinstance(v, unicode)) and isinstance(v, str):
                try:
                    status[k] = unicode(v)
                except:
                    raise Exception('Non Unicode for key:%s' % (k, ))
    return status

def get_categories(torrent_list):
    trackers = [(torrent['category'] or 'unknown') for torrent in torrent_list]
    categories = {}
    for tracker in trackers:
        categories[tracker] = categories.get(tracker,0) + 1
    return categories

def filter_torrent_state(torrent_list,filter_name):
    filters = {
        'downloading': lambda t: (not t.paused and not t.is_seed)
        ,'queued':lambda t: (t.paused and not t.user_paused)
        ,'paused':lambda t: (t.user_paused)
        ,'seeding':lambda t:(t.is_seed and not t.paused )
        ,'traffic':lambda t: (t.download_rate > 0 or t.upload_rate > 0)
    }
    filter_func = filters[filter_name]
    return [t for t in torrent_list if filter_func(t)]

#/utils

#template-defs:

def get_category_choosers(torrent_list):
    """
    todo: split into 2 parts...
    """
    categories = get_categories(torrent_list)

    filter_tabs = [Storage(title='All (%s)' % len(torrent_list),
            filter='', category=None)]

    #static filters
    for title, filter_name in [
        (_('Downloading'),'downloading') ,
        (_('Queued'),'queued') ,
        (_('Paused'),'paused') ,
        (_('Seeding'),'seeding'),
        (_('Traffic'),'traffic')
        ]:
        title += ' (%s)' % (
            len(filter_torrent_state(torrent_list, filter_name)), )
        filter_tabs.append(Storage(title=title, filter=filter_name))

    categories = [x for x in  get_categories(torrent_list).iteritems()]
    categories.sort()

    #trackers:
    category_tabs = []
    category_tabs.append(
        Storage(title=_('Trackers'),category=''))
    for title,count in categories:
        category = title
        title += ' (%s)' % (count, )
        category_tabs.append(Storage(title=title, category=category))

    return  filter_tabs, category_tabs

def category_tabs(torrent_list):
    filter_tabs, category_tabs = get_category_choosers(torrent_list)
    return ws.render.part_categories(filter_tabs, category_tabs)


def template_crop(text, end):
    if len(text) > end:
        return text[0:end - 3] + '...'
    return text

def template_sort_head(id,name):
    #got tired of doing these complex things inside templetor..
    vars = web.input(sort = None, order = None)
    active_up = False
    active_down = False
    order = 'down'

    if vars.sort == id:
        if vars.order == 'down':
            order = 'up'
            active_down = True
        else:
            active_up = True

    return ws.render.sort_column_head(id, name, order, active_up, active_down)

def template_part_stats():
    return ws.render.part_stats(get_stats())

def get_config(var):
    return ws.config.get(var)

irow = 0
def altrow(reset = False):
    global irow
    if reset:
        irow = 1
        return
    irow +=1
    irow = irow % 2
    return "altrow%s" % irow


template.Template.globals.update({
    'sort_head': template_sort_head,
    'part_stats':template_part_stats,
    'category_tabs':category_tabs,
    'crop': template_crop,
    '_': _ , #gettext/translations
    'str': str, #because % in templetor is broken.
    'int':int,
    'sorted': sorted,
    'altrow':altrow,
    'get_config': get_config,
    'self_url': self_url,
    'fspeed': common.fspeed,
    'fsize': common.fsize,
    'render': ws.render, #for easy resuse of templates
    'rev': 'rev.%s'  % (REVNO, ),
    'version': VERSION,
    'getcookie':getcookie,
    'get': lambda (var): getattr(web.input(**{var:None}), var) # unreadable :-(
})
#/template-defs

def create_webserver(urls, methods):
    from lib.webpy022.request import webpyfunc
    from lib.webpy022 import webapi
    from lib.gtk_cherrypy_wsgiserver import CherryPyWSGIServer
    import os

    func = webapi.wsgifunc(webpyfunc(urls, methods, False))
    server_address=("0.0.0.0", int(ws.config.get('port')))

    server = CherryPyWSGIServer(server_address, func, server_name="localhost")
    if ws.config.get('use_https'):
        server.ssl_certificate = os.path.join(ws.webui_path,'ssl/deluge.pem')
        server.ssl_private_key = os.path.join(ws.webui_path,'ssl/deluge.key')

    print "http://%s:%d/" % server_address
    return server

#------
__all__ = ['deluge_page_noauth', 'deluge_page', 'remote',
    'auto_refreshed', 'check_session',
    'do_redirect', 'error_page','start_session','getcookie'
    ,'setcookie','create_webserver','end_session',
    'get_torrent_status', 'check_pwd','static_handler','get_categories'
    ,'template','filter_torrent_state','log']
