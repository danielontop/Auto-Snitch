import logging, os , datetime , time , json , threading , requests , httpx , tls_client
snitchSettings = {
	'guildID': '',
	'channelId' : '',
    'proxy' : 'clockwrks:autoSnitch@3333.4444.555:2010', # Use a Rotating Proxy
    'token' : '',
    'webhook' : '',
}
guildId, channelId  , proxy , token , webhook = snitchSettings['guildID'] , snitchSettings['channelId'] , snitchSettings['proxy'] , snitchSettings['token'] , snitchSettings['webhook']

try: import websocket
except:
    os.system("pip install websocket-client")

logging.basicConfig(

    level=logging.INFO,
    format="\x1b[38;5;9m[\x1b[0m%(asctime)s\x1b[38;5;9m]\x1b[0m %(message)s\x1b[0m",
    datefmt="%H:%M:%S"
)

class Utils:
    def rangeCorrector(ranges):
        if [0, 99] not in ranges:
            ranges.insert(0, [0, 99])
        return ranges

    def getRanges(index, multiplier, memberCount):
        initialNum = int(index*multiplier)
        rangesList = [[initialNum, initialNum+99]]
        if memberCount > initialNum+99:
            rangesList.append([initialNum+100, initialNum+199])
        return Utils.rangeCorrector(rangesList)

    def parseGuildMemberListUpdate(response):
        memberdata = {
            "online_count": response["d"]["online_count"],
            "member_count": response["d"]["member_count"],
            "id": response["d"]["id"],
            "guild_id": response["d"]["guild_id"],
            "hoisted_roles": response["d"]["groups"],
            "types": [],
            "locations": [],
            "updates": []
        }

        for chunk in response['d']['ops']:
            memberdata['types'].append(chunk['op'])
            if chunk['op'] in ('SYNC', 'INVALIDATE'):
                memberdata['locations'].append(chunk['range'])
                if chunk['op'] == 'SYNC':
                    memberdata['updates'].append(chunk['items'])
                else:
                    memberdata['updates'].append([])
            elif chunk['op'] in ('INSERT', 'UPDATE', 'DELETE'):
                memberdata['locations'].append(chunk['index'])
                if chunk['op'] == 'DELETE':
                    memberdata['updates'].append([])
                else:
                    memberdata['updates'].append(chunk['item'])

        return memberdata


class DiscordSocket(websocket.WebSocketApp):
    def __init__(self, token, guild_id, channel_id):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.blacklisted_roles, self.blacklisted_users = [], []
        with open("./data/config.json") as f:
            blacklisted = json.load(f)
        for i in blacklisted["blacklistedRoles"]:
            self.blacklisted_roles.append(str(i))
        for i in blacklisted["blacklistedUsers"]:
            self.blacklisted_users.append(str(i))

        self.socket_headers = {
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0",
        }
        super().__init__(
            "wss://gateway.discord.gg/?encoding=json&v=9",
            header = self.socket_headers,
            on_open = lambda ws: self.sock_open(ws),
            on_message = lambda ws, msg: self.sock_message(ws, msg),
            on_close = lambda ws, close_code, close_msg: self.sock_close(
            ws, close_code, close_msg)
        )

        self.endScraping = False

        self.guilds = {}
        self.members = {}

        self.ranges = [[0, 0]]
        self.lastRange = 0
        self.packets_recv = 0

    def run(self):
        self.run_forever()
        return self.members 

    def scrapeUsers(self):
        if self.endScraping == False:
            self.send('{"op":14,"d":{"guild_id":"' + self.guild_id +
                      '","typing":true,"activities":true,"threads":true,"channels":{"' + self.channel_id + '":' + json.dumps(self.ranges) + '}}}')

    def sock_open(self, ws):
        self.send('{"op":2,"d":{"token":"' + self.token + '","capabilities":125,"properties":{"os":"Windows","browser":"Firefox","device":"","system_locale":"it-IT","browser_user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:94.0) Gecko/20100101 Firefox/94.0","browser_version":"94.0","os_version":"10","referrer":"","referring_domain":"","referrer_current":"","referring_domain_current":"","release_channel":"stable","client_build_number":103981,"client_event_source":null},"presence":{"status":"online","since":0,"activities":[],"afk":false},"compress":false,"client_state":{"guild_hashes":{},"highest_last_message_id":"0","read_state_version":0,"user_guild_settings_version":-1,"user_settings_version":-1}}}')

    def heartbeatThread(self, interval):
        try:
            while True:
                self.send('{"op":1,"d":' + str(self.packets_recv) + '}')
                time.sleep(interval)
        except Exception as e:
            pass
            return 

    def sock_message(self, ws, message):
        decoded = json.loads(message)

        if decoded is None:
            return

        if decoded["op"] != 11:
            self.packets_recv += 1

        if decoded["op"] == 10:
            threading.Thread(target=self.heartbeatThread, args=(
                decoded["d"]["heartbeat_interval"] / 1000, ), daemon=True).start()

        if decoded["t"] == "READY":
            for guild in decoded["d"]["guilds"]:
                self.guilds[guild["id"]] = {
                    "member_count": guild["member_count"]}

        if decoded["t"] == "READY_SUPPLEMENTAL":
            self.ranges = Utils.getRanges(
                0, 100, self.guilds[self.guild_id]["member_count"])
            self.scrapeUsers()

        elif decoded["t"] == "GUILD_MEMBER_LIST_UPDATE":
            parsed = Utils.parseGuildMemberListUpdate(decoded)

            if parsed['guild_id'] == self.guild_id and ('SYNC' in parsed['types'] or 'UPDATE' in parsed['types']):
                for elem, index in enumerate(parsed["types"]):
                    if index == "SYNC":
                        if len(parsed['updates'][elem]) == 0:
                            self.endScraping = True
                            break

                        for item in parsed["updates"][elem]:
                            if "member" in item:
                                mem = item["member"]
                                logging.info("Synced %s / %s" % (mem["user"]["id"], len(self.members)))
                                obj = {"tag": mem["user"]["username"] + "#" +
                                              mem["user"]["discriminator"], "id": mem["user"]["id"]}
                                if not set(self.blacklisted_roles).isdisjoint(mem['roles']):
                                    logging.info("%s#%s has a blacklisted role" % (mem["user"]["username"]) , mem["user"]["discriminator"])
                                else:
                                    if not mem["user"].get("bot"):
                                        if not mem["user"]["id"] in self.blacklisted_users:
                                            self.members[mem["user"]["id"]] = obj
                                        else:
                                            logging.info("%s#%s is a blacklisted user" % (mem["user"]["username"]) , mem["user"]["discriminator"])
                                    else:
                                        logging.info("%s#%s is a bot"  % (mem["user"]["username"]), mem["user"]["discriminator"])


                    elif index == "UPDATE":
                        for item in parsed["updates"][elem]:
                            if "member" in item:
                                mem = item["member"]
                                logging.info("Synced %s / %s" % (mem["user"]["id"], len(self.members)))
                                obj = {"tag": mem["user"]["username"] + "#" +
                                              mem["user"]["discriminator"], "id": mem["user"]["id"]}
                                if not set(self.blacklisted_roles).isdisjoint(mem['roles']):
                                    logging.info("%s#%s has a blacklisted role" % (mem["user"]["username"]) , mem["user"]["discriminator"])
                                else:
                                    if not mem["user"].get("bot"):
                                        if not mem["user"]["id"] in self.blacklisted_users:
                                            self.members[mem["user"]["id"]] = obj
                                        else:
                                           logging.info("%s#%s is a blacklisted user" % (mem["user"]["username"]) , mem["user"]["discriminator"])
                                    else:
                                        logging.info("%s#%s is a bot"  % (mem["user"]["username"]), mem["user"]["discriminator"])

                    self.lastRange += 1
                    self.ranges = Utils.getRanges(
                        self.lastRange, 100, self.guilds[self.guild_id]["member_count"])
                    # time.sleep(0.35)
                    self.scrapeUsers()

            if self.endScraping:
                self.close()

    def sock_close(self, ws, close_code, close_msg):
        pass


def autoSnitch(token, guild_id, channel_id):
    sb = DiscordSocket(token, guild_id, channel_id)
    return sb.run()

def rotateProxy():
    return {
        'http': 'http://%s' % proxy,
        'https': 'http://%s' % proxy
    }
def session(token):
    session = tls_client.Session(client_identifier='chrome_105')
    session.headers.update({
        'accept': '*/*',
        'accept-encoding': 'application/json',
        'accept-language': 'en-US,en;q=0.8',
        'Content-Type': 'application/json',
        'Authorization': token,
        'referer': 'https://discord.com/channels/@me',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
        'x-context-properties': 'eyJsb2NhdGlvbiI6IlVzZXIgUHJvZmlsZSJ9',
        'x-debug-options': 'bugReporterEnabled',
        'x-discord-locale': 'en-US',
        'x-super-properties': 'eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiRGlzY29yZCBDbGllbnQiLCJyZWxlYXNlX2NoYW5uZWwiOiJjYW5hcnkiLCJjbGllbnRfdmVyc2lvbiI6IjEuMC41OSIsIm9zX3ZlcnNpb24iOiIxMC4wLjIyNjIxIiwib3NfYXJjaCI6Ing2NCIsInN5c3RlbV9sb2NhbGUiOiJlbi1VUyIsImNsaWVudF9idWlsZF9udW1iZXIiOjE4MTk2NywibmF0aXZlX2J1aWxkX251bWJlciI6MzA4NTIsImNsaWVudF9ldmVudF9zb3VyY2UiOm51bGwsImRlc2lnbl9pZCI6MH0='
    })
    return session


def friend(userId):
    try:
        with open('tokens.txt', 'r') as TokenFiles:
            loadedTokens = TokenFiles.readlines()
            for tokens in loadedTokens:
                token = tokens.strip()
                sessionToken = session(token)
                addUserID = sessionToken.put('https://discord.com/api/v9/users/@me/relationships/%s' % userId, json={} , proxy = rotateProxy())
                if addUserID.status_code in [200, 204, 201]:
                    print('Added relationship successfully')
                elif addUserID.status_code in [429]:
                    retryTime = addUserID.json()['retry_after']
                    time.sleep(retryTime)
                    session.put('https://discord.com/api/v9/users/@me/relationships/%s' % userId, json = {}, proxy = rotateProxy())
    except Exception as Err:
        print(Err)

if __name__ == '__main__':
    currentMembers = set(autoSnitch('%s' % token,guildId, channelId))
    while True:
        newMembers = autoSnitch('%s' % token, guildId, channelId)
        newUser = [member for member in newMembers if member not in currentMembers]
        if newUser:
            for member in newUser:
                sessionSnitch = session(token)
                joinedTime = sessionSnitch.get('https://discord.com/api/v9/guilds/%s/members/%s' % (guildId, member))
                try:
                    joinDate = joinedTime.json()['joined_at'] ; minTime = datetime.timedelta(seconds = 150) ;  currentTime = datetime.datetime.now(datetime.timezone.utc) ;  newTime = datetime.datetime.fromisoformat(joinDate)
                    timeDifference = currentTime - newTime
                    if timeDifference <= minTime:
                        logging.info("User ID: %s is new to the Server" % member)
                        response = sessionSnitch.get('https://discord.com/api/v9/users/%s' % member).json()
                        tag = '%s#%s' % (response['username'], response['discriminator'])
                        guildName = sessionSnitch.get('https://discord.com/api/v9/guilds/%s' % guildId).json()['name']
                        response = sessionSnitch.get('https://discord.com/api/v9/users/%s' % member).json()
                        userTag = '%s#%s' % (response['username'], response['discriminator'])
                        joinedTime = sessionSnitch.get('https://discord.com/api/v9/guilds/%s/members/%s' % (guildId, member))
                        formatTime = newTime.strftime("%I:%M %p")
                        formatDate = newTime.strftime("%m-%d-%Y")
                        formatTimeandDate = "%s on %s" % (formatDate, formatTime)
                        payload = {
                            "content": "@here New User Joined %s" % guildId,
                            "embeds": [
                                {
                                    "color": 161791,
                                    "author": {"name": "Snitched Successful"},
                                    "timestamp": str(datetime.datetime.utcnow()),
                                    "fields": [
                                        {"name": "Version", "value": "On Join"},
                                        {"name": "Server Join Time", "value": str(formatTimeandDate)},
                                        {
                                            "name": "Username/Tag | User Id",
                                            "value": "%s | %s" % (userTag, member),
                                        },
                                        {"name": "Mention", "value": "<@%s>" % (member)},
                                        {
                                            "name": "Guild Name | Guild ID",
                                            "value": "%s | %s" % (guildName, guildId),
                                        },
                                    ],
                                    "thumbnail": {
                                        "url": "https://cdn.discordapp.com/avatars/%s/%s.png"
                                        % (member, response["avatar"])
                                    },
                                }
                            ],
                        }
                        requests.post('%s' % webhook, json = payload)
                        for i in range(10):
                            threading.Thread(target = friend, args = (member,)).start()
                except Exception as Err:
                    print(Err)
                    continue
        currentMembers = newMembers
        time.sleep(3)