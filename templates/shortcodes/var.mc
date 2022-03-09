<%page args="varname, default=''" />\
<%! import re %>\
<%
    val = default
    if re.match(r'^[a-zA-Z0-9_\.\[\]\'"]+$', varname):
        cur = context.kwargs
        dotparts = varname.split('.')
        try:
            for dp in dotparts:
                if dp in cur:
                    cur = cur.get(dp)
                elif '[' in dp:
                    init, scr_str = re.split(r'\[[\'"]?', dp, 2)
                    scr_str = re.sub(r'[\'"]?\]$', '', scr_str)
                    subscripts = re.split(r'[\'"]?\]\[[\'"]?', scr_str)
                    cur = cur.get(init)
                    if cur is None:
                        break
                    for scr in subscripts:
                        if scr.isdigit():
                            cur = cur[int(scr)] if isinstance(cur, list) else default
                        else:
                            cur = cur.get(scr, default)
                else:
                    cur = default
                    break
            val = cur
        except Exception as e:
            print("var shortcode error for", varname, ":", e)
            val = default
    else:
        print("ERROR:", varname)
    if val is None:
        val = default
%>\
${ val }\
