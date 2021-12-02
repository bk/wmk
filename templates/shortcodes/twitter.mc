<%page args="tweet_id" />
<%! import requests %>
<%
tweet_id = str(tweet_id)
if tweet_id.startswith('http'):
    tweet_id = tweet_id.strip('/').split('/')[-1]
tweet = requests.get(
    "https://api.twitter.com/1/statuses/oembed.json?id={}".format(tweet_id)).json()
%>
${ tweet['html'] }
