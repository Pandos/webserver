# CTK: Cherokee Toolkit
#
# Authors:
#      Alvaro Lopez Ortega <alvaro@alobbs.com>
#
# Copyright (C) 2009 Alvaro Lopez Ortega
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 2 of the GNU General Public
# License as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

import re
import json
import pyscgi
import threading
import Cookie

from Post import Post
from HTTP import HTTP_Response, HTTP_Error


class PostValidator:
    def __init__ (self, post, validation_list):
        self.post            = post
        self.validation_list = validation_list

    def Validate (self):
        errors  = {}
        updates = {}

        for key in self.post:
            key_done = False

            for regex, func in self.validation_list:
                if key_done: break

                if re.match(regex, key):
                    key_done = True

                    for n in range(len(self.post[key])):
                        val = self.post[key][n]
                        try:
                            tmp = func (val)
                        except Exception, e:
                            errors[key] = str(e)
                            break

                        if tmp:
                            self.post[key][n] = tmp
                            updates[key] = tmp

        if errors or updates:
            return {'ret': "unsatisfactory",
                    'errors':  errors,
                    'updates': updates}


class ServerHandler (pyscgi.SCGIHandler):
    def __init__ (self, *args):
        self.response = HTTP_Response()

        # SCGIHandler.__init__ invokes ::handle()
        pyscgi.SCGIHandler.__init__ (self, *args)

    def _process_post (self):
        pyscgi.SCGIHandler.handle_post(self)
        post = Post (self.post)
        return post

    def _render_page_ret (self, ret):
        # <int>  - HTTP Error <int>
        # <dict> - JSON <dict>
        # <str>  - 200, HTTP <str>
        # <list> - [
        None

    def _do_handle (self):
        # Read the URL
        url = self.env['REQUEST_URI']

        # Get a copy of the server (it did fork!)
        server = get_server()

        # Refer SCGI object by thread
        my_thread = threading.currentThread()
        my_thread.scgi_conn   = self
        my_thread.request_url = url

        for published in server._web_paths:
            if re.match (published._regex, url):
                # POST
                if published._method == 'POST':
                    post = self._process_post()
                    my_thread.post = post

                    # Validate
                    validator = PostValidator (post, published._validation)
                    errors = validator.Validate()
                    if errors:
                        resp = HTTP_Response(200, body=json.dumps(errors))
                        resp['Content-Type'] = "application/json"
                        return resp

                # Execute handler
                ret = published (**published._kwargs)

                # Deal with the returned info
                if type(ret) == str:
                    self.response += ret
                    return self.response

                elif type(ret) == dict:
                    info = json.dumps(ret)
                    self.response += info
                    self.response['Content-Type'] = "application/json"
                    return self.response

                elif isinstance(ret, HTTP_Response):
                    return ret

                else:
                    self.response += ret
                    return self.response

        # Not found
        return HTTP_Error (404)

    def handle_request (self):
        content = self._do_handle()
        self.send(str(content))


class Server:
    def __init__ (self):
        self._web_paths = []
        self._scgi      = None
        self._is_init   = False

    def init_server (self, *args, **kwargs):
        # Is it already init?
        if self._is_init:
            return
        self._is_init = True

        # Instance SCGI server
        self._scgi = pyscgi.ServerFactory (*args, **kwargs)

    def sort_routes (self):
        def __cmp(x,y):
            lx = len(x._regex)
            ly = len(y._regex)
            return cmp(ly,lx)

        self._web_paths.sort(__cmp)

    def add_route (self, route_obj):
        self._web_paths.append (route_obj)
        self.sort_routes()

    def serve_forever (self):
        try:
            while True:
                # Handle request
                self._scgi.handle_request()
        except KeyboardInterrupt:
            print "\r", "Server exiting.."
            self._scgi.server_close()


#
# Helpers
#

__global_server = None
def get_server():
    global __global_server
    if not __global_server:
        __global_server = Server ()

    return __global_server

def run (*args, **kwargs):
    srv = get_server()

    kwargs['handler_class'] = ServerHandler
    srv.init_server (*args, **kwargs)
    srv.serve_forever()


class Publish_FakeClass:
    def __init__ (self, func):
        self.__func = func

    def __call__ (self, *args, **kwargs):
        return self.__func (*args, **kwargs)


def publish (regex_url, klass, **kwargs):
    # Instance object
    if type(klass) == type(lambda: None):
        obj = Publish_FakeClass (klass)
    else:
        obj = klass()

    # Set internal properties
    obj._kwargs     = kwargs
    obj._regex      = regex_url
    obj._validation = kwargs.pop('validation', [])
    obj._method     = kwargs.pop('method', None)

    # Register
    server = get_server()
    server.add_route (obj)



class _Cookie:
    def __setitem__ (self, name, value):
        my_thread = threading.currentThread()
        response = my_thread.scgi_conn.response
        response['Set-Cookie'] = "%s=%s" %(name, value)

    def get_val (self, name, default=None):
        my_thread = threading.currentThread()
        scgi = my_thread.scgi_conn
        cookie = Cookie.SimpleCookie(scgi.env.get('HTTP_COOKIE', ''))
        if name in cookie:
            return cookie[name].value
        else:
            return default

    def __getitem__ (self, name):
        return self.get_val (name, None)


class _Post:
    def get_val (self, name, default=None):
        my_thread = threading.currentThread()
        post = my_thread.post
        return post.get_val(name, default)

    def __getitem__ (self, name):
        return self.get_val (name, None)


class _Request:
    def _get_request_url (self):
        my_thread = threading.currentThread()
        return my_thread.request_url

    url = property (_get_request_url)


cookie  = _Cookie()
post    = _Post()
request = _Request()
