<%page args="src, figtitle=None, img_link=None, link_target=None, caption=None, alt=None,  credit=None, credit_link=None, width=None, height=None, resize=False, css_class=None" />
<%! import markdown, os %>
<%namespace name="resiz" file="resize_image.mc" />
<%
if caption is None:
    caption = alt
if alt is None:
    alt = caption or ''
resize_opt = {'path': src, 'width': width, 'height': height}
if resize and isinstance(resize, dict):
    resize_opt.update(resize)
if resize:
    resize_kwargs = context.kwargs
    resize_kwargs.update(resize_opt)
    src = capture(lambda: resiz.body(**resize_kwargs))
if not src.startswith(('/', 'http:', 'https:')):
    src = os.path.normpath(os.path.join(os.path.dirname(SELF_URL), src))
%>
<figure${ ' class="{}"'.format(css_class) if css_class else '' }>
  % if img_link:
    <a href="${img_link}"${ ' target="{}"'.format(link_target) if link_target else '' }>
  % endif
  <img src="${src}" alt="${alt}"${ ' width="{}"'.format(width) if width else '' }${ ' height="{}"'.format(height) if height else '' }>
  % if link:
    </a>
  % endif
  % if figtitle or caption or credit:
    <figcaption>
      % if figtitle:
        <h4>${ figtitle }</h4>
      % endif
      % if caption:
        <div class="caption">${ markdown.markdown(caption) }</div>
      % endif
      % if credit and credit_link:
        <div class="credit"><a href="${ credit_link }">${ markdown.markdown(credit)  }</a></div>
      % elif credit:
        <div class="credit">${ markdown.markdown(credit)  }</div>
      % endif
  % endif
    </figcaption>
</figure>
