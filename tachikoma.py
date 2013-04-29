'''
A Basic parser to replace Jekyll

oni@section9.co.uk

'''

import sys, os, argparse, yaml, shutil, time
import markdown, threading, signal
from http.server import HTTPServer, BaseHTTPRequestHandler, SimpleHTTPRequestHandler

from distutils import dir_util
from jinja2 import Template, Environment, DictLoader
from datetime import datetime


class Atomizer():
  '''Create an atom.xml file for feeds '''

  def __init__(self,tachikoma):

    self.tachikoma = tachikoma

  def generate(self):


    self.content = '''<?xml version="1.0" encoding="utf-8"?>
      <feed xmlns="http://www.w3.org/2005/Atom">
    '''

    self.content += "<title>" + self.tachikoma.site.title + "</title>\n"
    self.content += "<link href=\"" + self.tachikoma.site_url + "/atom.xml\" />\n"
    self.content += "<updated>" + datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ") + "</updated>\n"

    for post in self.tachikoma.posts:
      self.content += "<entry>\n"
      self.content += "<title>" + post.title + "</title>\n"
      self.content += "<link href=\"" + self.tachikoma.site_url + "/posts/" + post.name   + ".html\" />\n"
      self.content += "<updated>" + post.date.strftime("%Y-%m-%dT%H:%M:%SZ") + "</updated>\n"
      
      self.content += "<title>" + post.title + "</title>\n"
      #self.content += "<content type=\"html\">" + post.rendered + "</content>\n"
      self.content += "<id>" + str(post.id) + "</id>"
      self.content += "</entry>\n"

    self.content += "</feed>\n"

    f = open(self.tachikoma.site_dir + "/atom.xml", "w")
    f.write(self.content)
    f.close()


class BuildThread(threading.Thread):
  ''' A thread to watch the directory, forcing a rebuild if things change '''

  def __init__(self,tachikoma):
    threading.Thread.__init__ ( self )
    self.tachikoma = tachikoma
    self.dirs = {}
    self.set_times()
    self.post_id = 0

  def set_times(self):
    for root, dirs, files in os.walk(self.tachikoma.dir):

      for name in files:
        # ignore special files for now
        if name[0] != ".":
          path = root + "/" + name
          self.dirs[path] = os.stat(path).st_mtime
    
  
  def run(self):
    self.running = True
    while self.running:
      time.sleep (2)
      for d in self.dirs.keys():
    
        if os.stat(d).st_mtime  != self.dirs[d]:
          self.tachikoma.read_layouts()
          self.tachikoma.copydirs()
          status, msg = self.tachikoma.build()
          print(msg)
          break
      self.set_times()
    


class MyRequestHandler( SimpleHTTPRequestHandler ):
  def do_GET(self,*args,**kwds):
    tmp = self.path.split('/')
    # redirect?
    if (len(tmp) == 3) and (tmp[0] == tmp[2]) and tmp[0] == '':
      self.send_response(301)
      self.send_header('Location', self.path + 'html/')
    else:
      SimpleHTTPRequestHandler.do_GET(self,*args,**kwds)


class Item():
  ''' 
  An item is either a blog post or a page
  '''
  def __init__(self):
    self.date = datetime.now()


class Tachikoma():
  ''' build the actual site '''

  def __init__(self, directory):
    ''' Perform the intial setup with the directory''' 
    self.error_msg(self.set_working_dir(directory))
    self.site_url = "http://www.section9.co.uk"

  def read_layouts(self):
    ''' Scan for and read in layouts - memory intensive? probably not '''
    layout_dict = {}
    for fn in os.listdir(self.layout_dir):
      f = open(self.layout_dir + "/" + fn)
      name, extension = os.path.splitext(fn)
      layout_dict[name] = f.read()
      f.close()
    # Load the layouts into the environment so jinja can find them
    self.jinja_env = Environment(extensions=['jinja2.ext.loopcontrols'], 
                                 loader=DictLoader(layout_dict));

  def parse_item(self, path):
    # Start with the YAML front matter - build a dictionary on metadata
    if not os.path.isfile(path):
      return (False, "Ignoring directory " + path)
    f = open(path)

    try:
      lines = f.readlines()
    except:
      return (False, "File is not an item: " + path)

    first = False
    found = False

    yaml_raw = ""
    item_body = ""

    item = Item()
    item.path, item.ext = os.path.splitext(path)
    item.name = os.path.basename(item.path)
    item.id = self.post_id
    self.post_id += 1

    if item.ext != ".md" and item.ext != ".markdown" and item.ext != ".html" and item.ext != ".htm":
      return (False, "Can only work with Markdown or HTML containing a YAML header")

    for line in lines:
      if "---" in line: # this works but is a bit lame
        if not first:
          first = True
          continue          
        elif not found: # don't parse markdown horizontal rules '---'
          found = True
          continue

      if first and not found:
        yaml_raw += line
      else:
        item_body += line

    if not found:
      return (False, "Incorrect YAML front matter in file: " + path)
    
    item.metadata = yaml.safe_load(yaml_raw)
   
    f.close()

    # Attempt to find the date and title
    self.parse_file_name(item)

    # Test for REQUIRED metadata
    if not item.metadata["layout"]:
      return (False, "ERROR: no layout directive found in " + path)

    if item.metadata["layout"] not in self.jinja_env.list_templates():
      return(False , "ERROR: no matching layout " + item.metadata["layout"] + " found in " + self.layout_dir )
        
    # If markdown, set a raw step
    if item.ext == ".md" or item.ext == ".markdown":
      item.raw = item_body
    else:
      item.content = item_body
      
    # Programmatically add all the metadata
    for key in item.metadata.keys():
      setattr(item, key, item.metadata[key])

    # Now set the URL which matches the filename
    item.url = "/posts/" + item.name + ".html"
   
    return(True,item)


  def parse_file_name(self, item):
    '''
    Look at the file name to determine the date
    Format is year-month-day_title or year_month_day_title
    at the beginning of the file
    '''

    tokens = item.name.split("-")
    
    if len(tokens) < 4:
      tokens = item.name.split("_")

    if len(tokens) < 4:
      return
  
    item.date = datetime.strptime(tokens[0] + " " + tokens[1] + " " + tokens[2], "%Y %m %d") 
    item.title = " ".join(tokens[3:])



  def parse_items(self):

    ''' Scan the Item directory for pages '''

    self.post_id = 0

    # List level posts
    for fn in os.listdir(self.post_dir):
      result, item = self.parse_item(self.post_dir + "/" + fn)
      if not result:
        print(item)
        continue
     
      item.tpath = self.site_post_dir
      self.posts.append(item)

    # Top level pages
    for fn in os.listdir(self.dir):
      result, item = self.parse_item(self.dir + "/" + fn)
      if not result:
        print(item)
        continue
    
      item.tpath = self.site_dir
      self.pages.append(item)

    return (True,"Success")



  def build_items(self):
    ''' Perform the markdown and jinja2 steps on the raw Items and write to files '''

    def write_out(self,item):
      """Make the item into a jinja template, render it and write the output"""
      template = self.jinja_env.from_string(item.content)
      item.rendered = template.render(page=item, site=self.site)
      print ("Creating: " + item.tpath + "/" + item.name + ".html")
      f = open(item.tpath + "/" + item.name + ".html", "w")
      f.write(item.rendered)
      f.close()
    
    for item in self.posts:
      
      if item.ext == ".md" or item.ext == ".markdown":
        
        # this section tests for mdx-outline plugin for markdown, which section9 uses to create its masonry bricks
        # its useful if you want sections but you can simply comment this out and use markdown straight if you prefer
        #try:
        #  import mdx_outline
        #  foo_loaded = True
        #except ImportError:
        foo_loaded = False 
        
        if foo_loaded:
          item.content = markdown.markdown(item.raw, ['outline(wrapper_tag=div,omit_head=True, wrapper_cls=s%(LEVEL)d box)'])
        else:
          item.content = markdown.markdown(item.raw)

        # Since this is markdown, we cant add an extends statement so we set the whole thing as a content block
        item.content = "{% block content %}\n" + item.content + "{% endblock %}"
        item.content = "{{% extends '{0}' %}}\n".format(item.metadata["layout"]) + item.content
  
      write_out(self,item) 
    
     
    for item in self.pages:
      item.content = "{{% extends '{0}' %}}\n".format(item.metadata["layout"]) + item.content
      write_out(self,item)


  def set_working_dir(self, directory):
    if directory[0]== "/":
      self.dir = directory
    else:
      self.dir = os.getcwd() + "/" + directory
    self.post_dir = self.dir + "/_posts"
    self.site_dir = self.dir + "/_site"
    self.site_post_dir = self.dir + "/_site/posts"
    self.layout_dir = self.dir + "/_layouts"

    self.layouts = {}

    # Test directories exist

    if not os.path.exists(self.post_dir):
      return (False, "No Item Directory")
    if not os.path.exists(self.layout_dir ):
      return (False,"No Layout directory")
    
    self.read_layouts()

    return (True,"Success")
         


  def build(self):
    ''' Build the site from the given directory '''

    self.pages = []
    self.posts = []
    self.site = Item()
    
    # TODO Establish a method to set this in a global file
    # TODO Setup the site metadata first for the Items and such
    self.site.title = "Section9 dot co dot uk ltd"

    self.error_msg( self.parse_items() )

    # Sort Items by date
    self.posts.sort(key= lambda x: x.date, reverse=True)

    self.site.posts = self.posts
    self.build_items()
                    
    return (True,"Finished Building")

  def clean(self):
    ''' Remove the site and re-copy. Not called when the server is running '''

    if os.path.exists(self.site_dir):
      shutil.rmtree(self.site_dir)
    
    os.mkdir(self.site_dir)
    os.mkdir(self.site_post_dir)
    
    self.copydirs()


  def _recursive_overwrite(self, src, dest, ignore=None):
    if os.path.isdir(src):
      if not os.path.isdir(dest):
        os.makedirs(dest)
      files = os.listdir(src)
      
      if ignore is not None:
        ignored = ignore(src, files)
      else:
        ignored = set()
      for f in files:
        if f not in ignored:
          self._recursive_overwrite(os.path.join(src, f), os.path.join(dest, f), ignore)
    else:
      shutil.copyfile(src, dest)
  
  def copydirs(self):
    ''' copy any directories to the _site dir that arent special dirs '''
    for fn in os.listdir(self.dir):
      if os.path.isdir(self.dir + "/" + fn) and fn[0] != "_" and fn[0] != ".":
        print("Copying directory " + fn + " to " + self.site_dir)
        #dir_util.copy_tree(self.dir + "/" + fn, self.site_dir  + "/" + fn)
        self._recursive_overwrite(self.dir + "/" + fn, self.site_dir  + "/" + fn, ignore = shutil.ignore_patterns('.*', 'tmp*'))

  def error_msg(self,value):
    result, message = value
    if not result:
      print(message)
      quit()


if __name__ == "__main__":

  parser = argparse.ArgumentParser()
  parser.add_argument("directory", help="base directory of the blog")
  parser.add_argument("-s", "--server", action="store_true", help="run as a server")
  args = parser.parse_args()

  
  
  if args.directory and not args.server:
    t = Tachikoma(args.directory)
    t.clean()
    a = Atomizer(t)
    result, msg = t.build()
    a.generate()
    print (msg)
    quit()

  if args.directory and args.server:
    t = Tachikoma(args.directory)
    a = Atomizer(t)
    t.clean()
    result, msg = t.build()
    a.generate()
    print(msg)

    server_class = HTTPServer
    handler_class = MyRequestHandler
    server_address = ('', 8000)
    httpd = server_class(server_address, handler_class)
  
    s = BuildThread(t)
    
    def signal_handler(signal, frame):
      print('Quitting')
      s.running = False
      s.join()
      quit()

    signal.signal(signal.SIGINT, signal_handler)

    s.start()

    os.chdir(t.site_dir)
    httpd.serve_forever()
  
