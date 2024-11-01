<%page args="template, is_jinja=False, *args, **kwargs" />\
<%doc>
  Insert the output of calling a template file or template literal.
  If `template` contains whitespace, assumes source text.
  Otherwise, assumes `template` is the name of a template file to be
  looked up normally. For file-based templates, the template type
  follows the setting `jinja2_templates` in `wmk_config.yaml`. If that is
  set to true, then the template file must be Jinja2, otherwise it must
  be Mako. For string templates, the default is Mako irrespective of this
  setting. In order to handle the string as a Jinja2 template, the keyword
  argument `is_jinja` must be set to True.
</%doc>\
<%! from mako.template import Template %>\
<%
jinja_active = hasattr(LOOKUP, 'from_string')
tpl_is_mako = not jinja_active and not is_jinja
if "\n" in template or ' ' in template:
    # Assume template source text
    if is_jinja:
        if jinja_active:
            tpl = LOOKUP.from_string(template)
        else:
            # Limited functionality
            import jinja2
            tpl = jinja2.Template(template)
    else:
        tpl = Template(text=template, lookup=LOOKUP)
else:
    # Assume filename
    tpl = LOOKUP.get_template(template)
kw = {}
if context and hasattr(context, 'kwargs'):
    # Mako
    kw = context.kwargs
elif get_context:
    # Jinja (global function defined by wmk)
    kw = get_context()
kw.update(kwargs)
if tpl_is_mako:
    output = tpl.render(*args, **kw) or ''
else:
    # Jinja does not support positional arguments for render()
    output = tpl.render(**kw) or ''
    if args:
        print("WARNING: positional arguments", args, "discarded in template shortcode")
%>\
${ output |n}\
