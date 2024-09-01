<%page args="path, width, height, op=None, format='jpg', quality=0.8, webroot=None, self_url=None, focal_point=None" />\
<%!
import os
from hashlib import sha1
from PIL import Image, ImageOps

named_focal_points = {
  'center': (0.5, 0.5),
  'top': (0.0, 0.5),
  'top-left': (0.0, 0.0),
  'top-right': (0.0, 1.0),
  'bottom': (1.0, 0.5),
  'bottom-left': (1.0, 0.0),
  'bottom-right': (1.0, 1.0),
  'left': (0.5, 0.0),
  'right': (0.0, 0.5),
}
%>\
<%
if op and op not in ('fit_width', 'fit_height', 'fit', 'fill'):
    raise ValueError('Invalid op: {}'.format(op))
if not format in ('jpg', 'png'):
    raise ValueError('Invalid format: {}'.format(format))
if not quality <= 1.0 and quality > 0.0:
    raise ValueError('Invalid quality: {}'.format(quality))
# Only used for .fit(), i.e. scaling to exact size (op == 'fill')
if focal_point is None:
    focal_point = (0.5, 0.5)
elif focal_point in named_focal_points:
    focal_point = named_focal_points[focal_point]
width = int(width) if width else None
height = int(height) if height else None
if not (width or height):
    raise ValueError('Need either width or height (or both)')
if op is None and width and height:
    op = 'fill'
elif op is None:
    op = 'fit_width' if width else 'fit_height'
if not webroot:
    webroot = context.get('WEBROOT')
    if not webroot:
        raise Exception("Webroot unknown")
if not path.startswith('/'):
    # self_url is the url of tha page referencing the image
    if self_url is None:
        self_url = SELF_URL
    path = os.path.normpath(os.path.join(os.path.dirname(self_url), path))
full_path = os.path.join(webroot, path.strip('/'))
if not os.path.exists(full_path):
    print(f'ERROR [resize_image]: {full_path} does not exist (webroot={webroot})')
    return
hash = sha1('::'.join(
    [path, str(width), str(height), op, format,
     str(quality), str(focal_point)]).encode('utf-8')).hexdigest()
sizedir = '%sx%s' % (str(width or ''), str(height or ''))
full_dir, fn = os.path.split(full_path)
ext = '.' + format
if not fn.endswith(ext):
    fn += ext
bucket = hash[:2]
fn = hash + '-' + fn
dest = '/resized_images/' + sizedir + '/' + bucket + '/' + fn
target_path = os.path.join(context.get('site_leading_path', ''), dest.strip('/'))
if not target_path.startswith('/'):
    target_path = '/' + target_path
full_dest = os.path.join(webroot, dest.strip('/'))
if not os.path.exists(full_dest):
    target_dir = os.path.split(full_dest)[0]
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    im = Image.open(full_path)
    # Take account of Orientation Exif tag
    im = ImageOps.exif_transpose(im)
    if op == 'fill':
        im2 = ImageOps.fit(im, (width, height), centering=focal_point)
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
    if pil_format == 'JPEG' and im2.mode != 'RGB':
        im2 = im2.convert('RGB')
    pil_opt = {'quality': int(quality*100)} if format=='jpg' else {}
    im2.save(full_dest, pil_format, **pil_opt)
%>\
${ target_path }\
