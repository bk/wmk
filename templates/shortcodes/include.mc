<%page args="filename, fallback=''" />\
<% import os %>
<%
if filename.startswith('/'):
    mybase = CONTENTDIR
else:
    mybase = os.path.dirname(SELF_FULL_PATH)
filename = os.path.join(mybase, filename.strip('/'))
filename = os.path.normpath(filename)
fc = fallback
if filename.startswith(CONTENTDIR) and os.path.exists(filename):
    with open(filename) as fh:
        fc = fh.read()
%>\
${ fc }\
