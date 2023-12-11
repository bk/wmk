<%page args="id, css_class=None, autoplay=False, title='Youtube Video', nowrap=False, nocookie=False, width=640, height=360" />
% if not nowrap:
<div${ ' class="{}"'.format(css_class) if css_class else ' style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden;"' }>
% endif
  <iframe src="https://www.youtube${ '-nocookie' if nocookie else '' }.com/embed/${ id }${ '?autoplay=1' if autoplay else '' }" ${ '' if css_class or nowrap else ' style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border:0;"' } allowfullscreen allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" width="${ width }" height="${ height }" title="${ title |h}"></iframe>
% if not nowrap:
</div>
% endif
