import urllib.request
import re

urls = [
    'https://tenor.com/view/anime-angry-pout-mad-cute-gif-17488206',
    'https://tenor.com/view/tsundere-anime-angry-pout-baka-gif-22287739',
    'https://tenor.com/view/toradora-taiga-aisaka-anime-angry-baka-gif-12961819',
    'https://tenor.com/view/anime-blush-cute-embarrassed-shy-gif-14639906',
    'https://tenor.com/view/blush-anime-tsundere-embarrassed-gif-16168502',
    'https://tenor.com/view/anime-embarrassed-blush-shy-nervous-gif-13834371',
    'https://tenor.com/view/hmph-anime-arms-crossed-pout-gif-11603511',
    'https://tenor.com/view/anime-hmph-turn-away-ignore-gif-14734693',
    'https://tenor.com/view/tsundere-turn-away-hmph-anime-gif-20050854'
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        match = re.search(r'content=\"(https://media\d*\.tenor\.com/[^\"]+\.gif)\"', html)
        if match:
            print(f"'{match.group(1)}',")
        else:
            print('# Not found for', url)
    except Exception as e:
        print('# Error', url, e)
