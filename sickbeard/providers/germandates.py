import re
from bs4 import BeautifulSoup
from lib import requests
from lib.sqlalchemy import *
from sickbeard import logger
from datetime import date, timedelta

##define a database and add stuff to it
engine = create_engine('sqlite:///germandates.db', echo=False)
metadata = MetaData(engine)

airdates = Table('airdates', metadata,
	Column('id', Integer, primary_key=True),
	Column('name', String),
	Column('firstaired', String),
	Column('tvdbid', Integer),
	Column('season', Integer),
	Column('episode', Integer),
	)

slugs = Table('slugs', metadata,
	Column('id', Integer, primary_key=True, unique=True),
	Column('name', String),
	Column('serienjunkies', String),
	Column('fernsehserien', String),
	)

version = Table('version', metadata,
	Column('id', Integer, primary_key=True),
	Column('nextupdate', Integer),
	)

metadata.create_all(engine)

conn = engine.connect()

# url = "http://www.fernsehserien.de/new-girl/episodenguide"
# tvdbid = 248682

### FIRST STEP: Get slugs from cytec.us



def updateSlugs():
	url = "http://cytec.us/tvdb/getList.php"
	r = requests.get(url)
	#print r
	logger.log(u"Updating german airdate slugs", logger.DEBUG)
	for entry in r.json["result"]:
	 	if not slugs.select(slugs.c.id == entry["id"]).execute().fetchone():
	 		slugs.insert().execute(entry)


def updateEpisode(serieselement):
	entry = airdates.select(and_(
		airdates.c.tvdbid == serieselement["tvdbid"], 
		airdates.c.season == serieselement["season"], 
		airdates.c.episode == serieselement["episode"]
		)).execute().fetchone()

	if not entry:
		#print u"Entry for {0} not in my Database... CREATE it".format(serieselement)
		logger.log(u"Entry for {0} not in my Database... CREATE it".format(serieselement), logger.DEBUG)
		airdates.insert(serieselement).execute()
	elif entry and not entry.firstaired:
		#print u"Entry for {0} without a Airdate... UPDATE it".format(serieselement)
		logger.log(u"Entry for {0} without a Airdate... UPDATE it".format(serieselement), logger.DEBUG)
		airdates.update().where(and_(airdates.c.season == serieselement["season"], airdates.c.episode == serieselement["episode"],airdates.c.tvdbid == serieselement["tvdbid"])).values(serieselement).execute()
		#print entry
	else:
		logger.log(u"Entry {0} is in my Database".format(entry), logger.DEBUG)
		#print u"Entry {0} is in my Database".format(entry)


#next try to get infos from an given tvdbid
#tvdbid=72023


def fsGetDates(tvdbid):
	myrequest = slugs.select(slugs.c.id == tvdbid).execute().fetchone()
	if not myrequest:
		# print "Sorry nothing found for this slug..."
		# print "Got to cytec.us/tvdb to add some..."
		logger.log(u"Sorry i cant find any slugs for {0}, go to cytec.us/tvdb to add more shows".format(tvdbid), logger.ERROR)
		updateSlugs()
	
	if myrequest:
		#fernseserien.de first...
		url = "http://www.fernsehserien.de/{0}/episodenguide".format(myrequest.fernsehserien)
		r = requests.get(url)
		if r.status_code == 200:
			#print r.text
			soup = BeautifulSoup(r.text)
			eplist = soup.find_all("tr", {"class": "ep-hover"})
			for row in eplist:
				info = row.find_all("td")
				if info:
					rawseason = info[1]["data-href"]
					regex = ".*guide\/.*?(\d{1,3})/.*"
					#print rawseason, regex
					season = re.match(regex, rawseason).group(1)
					episode = info[1].text
					name = info[3].text
					date = info[4].text
					serieselement = { "tvdbid": tvdbid, "name": name, "firstaired": date, "episode": episode, "season": season }
					updateEpisode(serieselement)
				else:
					#print "Something went wrong... unable to parse: {0}".format(row)
					logger.log(u"Something went wrong... unable to parse: {0}".format(row), logger.DEBUG)
		else:
			logger.log(u"Seems there was an error with the url {0}".format(url), logger.WARNING)

def sjGetDates(tvdbid):
	myrequest = slugs.select(slugs.c.id == tvdbid).execute().fetchone()
	if not myrequest:
		logger.log(u"Sorry i cant find any slugs for {0}, go to cytec.us/tvdb to add more shows".format(tvdbid), logger.ERROR)
		updateSlugs()
	
	if myrequest:
		#serienjunkies.de first...
		url = "http://www.serienjunkies.de/{0}/alle-serien-staffeln.html".format(myrequest.serienjunkies)
		r = requests.get(url)
		if r.status_code == 200:
			#print r.text
			soup = BeautifulSoup(r.text)
			eplist = soup.find("table", {"class": "eplist"})
			for row in eplist:
				info = row.find_all("td", {"class": re.compile("^e")})
				if info:
					season, episode = info[0].text.split("x")
					name = info[3].text
					date = info[4].text
					serieselement = { "tvdbid": tvdbid, "name": name, "firstaired": date, "episode": episode, "season": season }
					updateEpisode(serieselement)
				else:
					#print "Something went wrong... unable to parse: {0}".format(row)
					logger.log(u"Something went wrong... unable to parse: {0}".format(row), logger.WARNING)
		else:
			#print "Seems there was an error with the url {0}".format(url)
			logger.log(u"Seems there was an error with the url {0}".format(url), logger.WARNING)
	

#sjGetDates(72023)

def updateAirDates(tvdbid):
	now = date.today()
	t = timedelta(14)
	next = now + t
	result = version.select().execute().fetchone()
	#print result
	if not result:
		ins = {"id":1, "nextupdate":next.toordinal()}
		version.insert(ins).execute()
		#print result.lastupdate
		logger.log(u"Next AirDates update: {0}".format(next), logger.ERROR)
	#print "heute ist: {0}".format(now)
	if result and result.nextupdate >= now.toordinal():
		logger.log(u"Next AirDates update: {0}".format(date.fromordinal(result.nextupdate)), logger.ERROR)
	if result and result.nextupdate <= now.toordinal():
		#print "going to update..."
		logger.log(u"Running AirDates update", logger.ERROR)
		version.update().where(version.c.id == 1).values(nextupdate=next.toordinal()).execute()
		updateSlugs()
		fsGetDates(tvdbid)
		sjGetDates(tvdbid)



def getEpInfo(tvdbid, season, episode):
	
	if season == 0:
		return "1.1.1".split(".")

	result = airdates.select(and_(
		airdates.c.tvdbid == tvdbid, 
		airdates.c.season == season, 
		airdates.c.episode == episode
		)).execute().fetchone()
	#print u"{0}, {1}x{2} returned: {3}".format(tvdbid, season, episode, result)
	if not result:
		updateSlugs()
		fsGetDates(tvdbid)
		sjGetDates(tvdbid)

	elif not result.firstaired:
		return "1.1.1".split(".")
		updateAirDates(tvdbid)
	else:
		#print result.firstaired
		return result.firstaired.split(".")

#a = getEpInfo(72023, 1, 1)
#print a