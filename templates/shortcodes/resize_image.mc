<%page args="path, width, height, op='fill', format='jpg', quality=0.75" />\
<%!
import os
from hashlib import sha1
from PIL import Image, ImageOps
%>\
<%
if not op in ('fit_width', 'fit_height', 'fit', 'fill'):
    raise Exception('Invalid op: {}'.format(op))
if not format in ('jpg', 'png'):
    raise Exception('Invalid format: {}'.format(format))
if not quality <= 1.0 and quality > 0.0:
    raise Exception('Invalid quality: {}'.format(quality))
width = int(width)
height = int(height)
webroot = context.get('WEBROOT')
if not webroot:
    raise Exception("Webroot unknown")
full_path = os.path.join(webroot, path.strip('/'))
if not os.path.exists(full_path):
    raise Exception('{} does not exist (webroot={})'.format(full_path, webroot))
hash = sha1('::'.join(
    [path, str(width), str(height), op, format, str(quality)]).encode('utf-8')).hexdigest()
dest = '/resized_images/' + hash + '.' + format
target_path = os.path.join(context.get('site_leading_path', ''), dest.strip('/'))
if not target_path.startswith('/'):
    target_path = '/' + target_path
full_dest = os.path.join(webroot, dest.strip('/'))
if not os.path.exists(full_dest):
    target_dir = os.path.join(webroot, 'resized_images')
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    im = Image.open(full_path)
    if op == 'fill':
        im2 = ImageOps.fit(im, (width, height))
    else:
        w, h = im.size
        if op == 'fit_width':
            factor = width / w
        elif op == 'fit_height':
            factor = height / h
        else:
            wfac = width / w
            hfac = height / h
            factor = min([wfac, hfac])
        im2 = ImageOps.scale(im, factor)
    pil_format = 'JPEG' if format=='jpg' else 'PNG'
    pil_opt = {'quality': int(quality*100)} if format=='jpg' else {}
    im2.save(full_dest, pil_format, **pil_opt)
%>\
${ target_path }\