<%page args="template, *args, **kwargs" />\
<%doc>
  Insert the output of calling a template file or template literal.
  If `template` contains whitespace, assumes mako source text.
  Otherwise, assumes `template` is the name of a Mako file to be
  looked up normally.
</%doc>\
<%! from mako.template import Template %>\
<%
if "\n" in template or ' ' in template:
    # Assume template source text
    tpl = Template(text=template, lookup=LOOKUP)
else:
    # Assume filename
    tpl = LOOKUP.get_template(template)
kw = context.kwargs
kw.update(kwargs)
output = tpl.render(*args, **kw) or ''
%>\
${ output |n}\
