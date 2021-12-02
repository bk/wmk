<%page args="id, css_class=None, autoplay=False, dnt=False, muted=False, title='Vimeo Video'" />
<% params = '&'.join(_+'=1' for _ in [autoplay, dnt, muted] if _) %>
<div${ 'class="{}"'.format(css_class) if css_class else ' style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden;"' }>
  <iframe src="https://player.vimeo.com/video/${ id }${ '?'+params if params else '' }" ${ ' class="{}"'.format(css_class) if css_class else ' style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border:0;"' } allowfullscreen></iframe>
</div>
