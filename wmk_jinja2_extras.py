import importlib
import re
import datetime

import wmk_mako_filters as wmf



def get_globals():
    return {
        # Allows importing modules in templates like this:
        # {% set mymodule = import('mymodule') %}
        'import': importlib.import_module,
        # From wmk_mako_filters
        'markdownify': wmf.markdownify,
        'slugify': wmf.slugify,
        'strip_html': wmf.strip_html,
        'to_json': wmf.to_json,
        'date': wmf.date,
        # Note: url and fingerprint will be added to these
    }


def get_filters():
    return {
        'date_to_iso': wmf.date_to_iso,
        'date_to_rfc822': wmf.date_to_rfc822,
        'date': wmf.date,
        'date_short': wmf.date_short,
        'date_short_us': wmf.date_short_us,
        'date_long': wmf.date_long,
        'date_long_us': wmf.date_long_us,
        'markdownify': wmf.markdownify,
        'slugify': wmf.slugify,
        'truncate': wmf.truncate,
        'truncatewords': wmf.truncatewords,
        'p_unwrap': wmf.p_unwrap,
        'strip_html': wmf.strip_html,
        'cleanurl': wmf.cleanurl,
        'to_json': wmf.to_json,
        # TODO: add url here
    }
