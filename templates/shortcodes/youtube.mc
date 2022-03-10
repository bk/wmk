<%page args="id, css_class=None, autoplay=False, title='Youtube Video'" />
<div${ ' class="{}"'.format(css_class) if css_class else ' style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden;"' }>
  <iframe src="https://www.youtube.com/embed/${ id }${ '?autoplay=1' if autoplay else '' }" ${ '' if css_class else ' style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border:0;"' } allowfullscreen title="${ title }"></iframe>
</div>
