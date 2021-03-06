import datetime
import time
import re
from email.utils import formatdate  # rfc822

import markdown

from wmk_utils import slugify


__all__ = [
    'date_to_iso',
    'date_to_rfc822',
    'date',
    'date_short',
    'date_short_us',
    'date_long',
    'date_long_us',
    'slugify',
    'markdownify',
    'truncate',
    'truncatewords',
    'p_unwrap',
    'strip_html',
    'cleanurl',
]


def _ensure_datetime(d):
    """
    Converts dates, unix time stamps and ISO strings to datetime.
    Also handles the special strings 'now' and 'today'.
    """
    if isinstance(d, datetime.datetime):
        return d
    elif isinstance(d, datetime.date):
        return datetime.datetime(d.year, d.month, d.day)
    if isinstance(d, str) and d.isdigit():
        d = int(d)
    if isinstance(d, (int, float)):
        return datetime.datetime.fromtimestamp(d)
    elif isinstance(d, str):
        if d.lower() == 'now':
            return datetime.datetime.now()
        elif d.lower() == 'today':
            today = datetime.date.today()
            return datetime.datetime(today.year, today.month, today.day)
        try:
            return datetime.datetime.fromisoformat(d)
        except:
            pass
    return None


def date_to_iso(s=None, sep='T', upto='sec', with_tz=False):
    """
    Similar to Jekyll's date_to_xmlschema but more flexible.
    Examples:
      - 2008-11-07T13:07:54-08:00 (with sep='T', upto='sec', with_tz=True)
      - 2008-11-07 13:07 (with sep=' ', upto='min')
    """
    def inner(s):
        no_tz = not with_tz
        d = _ensure_datetime(s)
        if d is None:
            return s
        d = str(d)
        if sep and sep != ' ' and len(sep) == 1:
            d = d.replace(' ', sep, 1)
        tz = '+00:00'
        found = re.search(r'([-+]\d\d:\d\d)$', d)
        if found:
            tz = found.group(1)
        if upto.startswith('day'):
            no_tz = True
            d = d[:10]
        elif upto.startswith('min'):
            d = d[:16]
        elif upto.startswith('sec'):
            d = d[:19]
        if not no_tz:
            d += tz
        return d
    return inner if s is None else inner(s)


def date_to_rfc822(s):
    """
    Example: Thu, 5 Apr 2012 23:47:37 +0200
    """
    d = _ensure_datetime(s)
    if d is None:
        return s
    return formatdate(d)


def date_short(s):
    """
    E.g. 7 Nov 2008
    """
    d = _ensure_datetime(s)
    if d is None:
        return s
    return d.strftime('%-d %b %Y')


def date_short_us(s):
    """
    E.g. Nov 7th, 2008
    """
    d = _ensure_datetime(s)
    if d is None:
        return s
    if d.day in (1, 21, 31):
        return d.strftime('%b %-dst, %Y')
    elif d.day in (2, 22):
        return d.strftime('%b %-dnd, %Y')
    elif d.day in (3, 23):
        return d.strftime('%b %-drd, %Y')
    else:
        return d.strftime('%b %-dth, %Y')


def date_long(s):
    """
    E.g. 7 November 2008
    """
    d = _ensure_datetime(s)
    if d is None:
        return s
    return d.strftime('%-d %B %Y')


def date_long_us(s):
    """
    E.g. Nov 7th, 2008
    """
    d = _ensure_datetime(s)
    if d is None:
        return s
    if d.day in (1, 21, 31):
        return d.strftime('%B %-dst, %Y')
    elif d.day in (2, 22):
        return d.strftime('%B %-dnd, %Y')
    elif d.day in (3, 23):
        return d.strftime('%B %-drd, %Y')
    else:
        return d.strftime('%B %-dth, %Y')


def date(s=None, fmt=None):
    """
    Strftime filter. The default format is '%c'.
    """
    if not fmt:
        fmt = '%c'
    def inner(s):
        d = _ensure_datetime(s)
        return d.strftime(fmt)
    return inner if s is None else inner(s)


def markdownify(s=None, extensions=None):
    """
    Convert markdown to HTML.
    """
    if extensions is None:
        extensions = ['extra']
    def inner(s):
        return markdown.markdown(s, extensions=extensions)
    return inner if s is None else inner(s)


def truncate(s=None, length=200, ellipsis='???'):
    """
    Truncate to given number of characters. If any shortening occurs,
    an ellipsis will be appended. HTML tags will be stripped.
    """
    def inner(s):
        s_orig = strip_html(s)
        ret = s_orig[:length-1]
        if (len(ret) < len(s_orig)
                and s_orig[length] not in (' ', '.', '!', '?', ';', ':')):
            ret = re.sub(r' [^ ]*$', '', ret)
        if len(ret) < len(s_orig):
            ret += ellipsis
        return ret
    return inner if s is None else inner(s)


def truncatewords(s=None, length=25, ellipsis='???'):
    """
    Truncate to given number of words. If any shortening occurs,
    an ellipsis will be appended. HTML tags will be stripped.
    """
    def inner(s):
        s_orig = strip_html(s).split(' ')
        if len(s_orig) <= length:
            return ' '.join(s_orig)
        else:
            return ' '.join(s_orig[:length]) + ellipsis
    return inner if s is None else inner(s)


def p_unwrap(s):
    """
    Remove wrapping <p> tag - iff there is only one.
    Typically used like this: `${ short_text | markdownify,p_unwrap }`,
    so as to keep inline tags inside the paragraph but not the wrapping
    p tag.
    """
    s = s.strip()
    if s.startswith('<p>') and s.count('<p>') == 1:
        return s.replace('<p>','').replace('</p>', '').strip()


def strip_html(s):
    """
    Remove all html tags (converting markdown to html beforehand).
    TODO: handle entity and character references.
    """
    ret = markdownify()(s)
    # hidden tags:
    for tag in ('script', 'style', 'template', 'iframe', 'object'):
        rx = r'<' + tag + r'[^>]*>.*?</' + tag + r'[^>]*>'
        ret = re.sub(rx, '', ret, flags=re.IGNORECASE)
    # block tags (at least for our purposes)
    blocktags = ['address', 'article', 'blockquote', 'details', 'dialog',
                 'dd', 'div', 'dl', 'dt', 'fieldset', 'figcaption', 'figure',
                 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                 'header', 'img', 'hgroup', 'hr', 'li', 'main', 'nav', 'ol',
                 'p', 'pre', 'section', 'table', 'td', 'th', 'ul']
    rx = r'<+/?(?:' + '|'.join(blocktags) + r')[^>]*>'
    ret = re.sub(rx, ' ', ret, flags=re.IGNORECASE)
    # Inline tags
    ret = re.sub(r'<[^>]+>', '', ret, flags=re.IGNORECASE)
    return ret.strip()


def cleanurl(s):
    """
    Change /path/index.html to /path/.
    """
    if s.endswith('/index.html'):
        return s[:-10]
    return s
