<%page args="title, label=None, lang='en'" />
<%
title = title.replace(' ', '_')
if not label:
    label = title.replace('_', ' ')
%>
<a href="https://${ lang }.wikipedia.org/wiki/${ title |u }" class="wikipedia">${ label }</a>
