<%page args="src, title=None, link=None, caption=None, alt=None,  credit=None, credit_link=None, width=None, height=None, resize=False" />
<%! import markdown %>
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
%>
<figure${ ' class="{}"'.format(css_class) if css_class else '' }>
  % if link:
    <a href="${link}"${ ' target="{}"'.format(link_target) if link_target else '' }>
  % endif
  <img src="${src}" alt="${alt}"${ ' width="{}"'.format(width) if width else '' }${ ' height="{}"'.format(height) if height else '' }>
  % if link:
    </a>
  % endif
  % if title or caption or credit:
    <figcaption>
      % if title:
        <h4>${ title }</h4>
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
