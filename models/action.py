import hashlib
import time
import re

from core import logging, helpers, db, workers, model, cache
from core.models import action, conduct, trigger

from plugins.occurrence.models import occurrence
from plugins.occurrence.models import trigger as occurrenceTrigger

# Needs to be updated so that objects are cahced and then mass updated into the database on class __del__

class _occurrence(action._action):
    occurrenceMatchString = str()
    lullTime = int()
    lullTimeExpiredCount = int()
    dbSlowUpdate = bool()

    def __init__(self):
        # Used to cahce object loads and reduce database requests ( set to none some schema excludes them )
        cache.globalCache.newCache("occurrenceCache",maxSize=10485760)
        cache.globalCache.newCache("occurrenceCacheMatch",maxSize=10485760)
        cache.globalCache.get("occurrenceCache","all",getOccurrenceObjects)
        self.bulkClass = db._bulk()

    def postRun(self):
        self.bulkClass.bulkOperatonProcessing()

    def run(self,data,persistentData,actionResult):
        # Is this a clear event passed by the occurrence clear notifier?
        if "clearOccurrence" in data:
            actionResult["result"] = True
            actionResult["rc"] = 205
            return actionResult
        elif "000000000001010000000000" in str(self._id):
            actionResult["result"] = True
            actionResult["rc"] = 201
            actionResult["msg"] = "Occurrence ran within codify, always results in 201 created"
            return actionResult

        match = "{0}-{1}".format(self._id,helpers.evalString(self.occurrenceMatchString,{ "data" : data }))
        # Check for existing occurrence matches
        foundOccurrence = cache.globalCache.get("occurrenceCacheMatch",match,getOccurrenceObject,customCacheTime=self.lullTime,nullUpdate=True)
        if foundOccurrence == None:
            # Raising new occurrence and assuming the database took the object as expected
            newOccurrence = occurrence._occurrence().bulkNew(self,match,helpers.unicodeEscapeDict(data),self.acl,self.bulkClass)
            cache.globalCache.insert("occurrenceCacheMatch",match,newOccurrence)
            logging.debug("Occurrence Created async, actionID='{0}'".format(self._id),7)
            actionResult["result"] = True
            actionResult["rc"] = 201
            return actionResult
        else:
            if foundOccurrence._id != "":
                # Checking if we should only update db when less than half lullTime is left ( reduced db load )
                if self.dbSlowUpdate and (int(time.time()) - foundOccurrence.lastOccurrenceTime) < self.lullTime/2:
                    actionResult["result"] = True
                    actionResult["rc"] = 302
                    return actionResult
                # Updating existing occurrences
                foundOccurrence.lastOccurrenceTime = int(time.time())
                foundOccurrence.lullTime = (foundOccurrence.lastOccurrenceTime + self.lullTime)
                foundOccurrence.lullTimeExpired = self.lullTimeExpiredCount
                foundOccurrence.bulkUpdate(["lastOccurrenceTime","lullTime","lullTimeExpired"],self.bulkClass)
                actionResult["data"]["occurrenceData"] = foundOccurrence.data
                logging.debug("Occurrence Updated, occurrenceID='{0}' actionID='{1}'".format(foundOccurrence._id,self._id),7)
                actionResult["result"] = True
                actionResult["rc"] = 302
                return actionResult
            else:
                logging.debug("Occurrence Update Failed - NO ID, actionID='{0}'".format(self._id),7)
                actionResult["result"] = False
                actionResult["rc"] = 500
                return actionResult
                    
class _occurrenceClean(action._action):

    def run(self,data,persistentData,actionResult):
        now = int(time.time())
        conductsCache = {}
        foundOccurrenceCache = {}
        # Finding occurrences that have expired their lull time
        foundOccurrences = occurrence._occurrence().query(query={ "lullTime" : { "$lt" :  now}, "lullTimeExpired" : { "$lt" : 1 } }  )["results"]
        foundOccurrencesIDs = []
        for foundOccurrence in foundOccurrences:
            # Adding IDs of found occurrences to the delete list as they are now cleared
            foundOccurrencesIDs.append(db.ObjectId(foundOccurrence["_id"]))
            # Notifiying clears
            if foundOccurrence["occurrenceFlowID"] not in foundOccurrenceCache:
                tempOccurrence = _occurrence().load(foundOccurrence["occurrenceActionID"])
                foundOccurrenceCache[foundOccurrence["occurrenceFlowID"]] = { "triggerID": None, "conducts" : [] }

                if tempOccurrence.enabled:
                    conducts = conduct._conduct().query(query={"flow.actionID" : tempOccurrence._id, "flow.flowID" : foundOccurrence["occurrenceFlowID"],  "enabled" : True})["results"]
                    foundOccurrenceCache[foundOccurrence["occurrenceFlowID"]]["exitCodeMode"] = { "actionID": tempOccurrence._id, "conducts" : conducts }

            conducts = foundOccurrenceCache[foundOccurrence["occurrenceFlowID"]]["exitCodeMode"]["conducts"]
            data = conduct.flowDataTemplate()
            data["triggerID"] =  tempOccurrence._id
            data["clearOccurrence"] = True
            # If occurrence contains the orgnial data var and event then apply it to the data passsed to clear
            if "data" in foundOccurrence:
                data["event"] = foundOccurrence["data"]["event"]
                data["var"] = foundOccurrence["data"]["var"]
            for conduct_ in conducts:
                loadedConduct = None
                if conduct_["classID"] not in conductsCache:
                    # Dynamic loading for classType model
                    _class = model._model().get(conduct_["classID"]).classObject()
                    if _class:
                        loadedConduct = _class().load(conduct_["_id"])
                        conductsCache[conduct_["classID"]] = loadedConduct           
                    else:
                        logging.debug("Cannot locate occurrence by ID, occurrenceID='{0}'".format(foundOccurrence["occurrenceFlowID"]),6)
                else:
                    loadedConduct = conductsCache[conduct_["classID"]]

                if loadedConduct:
                    try:
                        cache.globalCache.delete("occurrenceCacheMatch",foundOccurrence["match"])
                        eventStat = { "first" : True, "current" : 0, "total" : 1, "last" : True }
                        tempData = conduct.copyFlowData(data)
                        tempData["eventStats"] = eventStat
                        loadedConduct.triggerHandler(foundOccurrence["occurrenceFlowID"],tempData,flowIDType=True)
                    except Exception as e:
                        pass # Error handling is needed here

        # Deleting expired occurrences
        if len(foundOccurrencesIDs) > 0:
            foundOccurrences = occurrence._occurrence().api_delete(query={"_id" : { "$in" : foundOccurrencesIDs } })
            logging.debug("Occurrences cleared, result='{0}'".format(foundOccurrences),7)

        activeOccurrences = occurrence._occurrence()._dbCollection.aggregate([
            {
                "$project": 
                { 
                    "triggerID" : { "$toObjectId" : '$triggerID' },
                    "lastLullCheck" : 1,
                    "lullTime" : 1
                }
            },
            {
                "$lookup" :
                {
                    "from" : "triggers",
                    "localField" : "triggerID",
                    "foreignField" : "_id",
                    "as" : "triggers"
                }
            },
            { 
                "$unwind" : "$triggers" 
            },
            {
                "$match" : 
                {
                    "lullTime" : { "$lt" :  now },
                    "$expr" : { "$gt" : [ "$triggers.lastCheck", "$lastLullCheck" ] }
                }
            }
        ])
        updateOccurrenceIDs = []
        for activeOccurrence in activeOccurrences:
            updateOccurrenceIDs.append(activeOccurrence["_id"])
        # Increment all with expired lullTime
        if len(updateOccurrenceIDs) > 0:
            incrementedOccurrences = occurrence._occurrence().api_update(query={ "_id" : { "$in" : updateOccurrenceIDs } },update={ "$inc" : { "lullTimeExpired" :  -1 }, "$set" : { "lastLullCheck" : int(time.time()) } } )
            logging.debug("Occurrences incremented, result='{0}'".format(incrementedOccurrences),7)

        actionResult["result"] = True
        actionResult["rc"] = 0
        return actionResult

def getOccurrenceObject(match,sessionData):
    foundOccurrences = cache.globalCache.get("occurrenceCache","all",getOccurrenceObjects)
    if foundOccurrences:
        if match in foundOccurrences:
            return foundOccurrences[match]
    return None

def getOccurrenceObjects(match,sessionData):
    foundOccurrences = occurrence._occurrence().getAsClass(query={},fields=["lastOccurrenceTime","lullTime","lullTimeExpired","match","data"])
    result = {}
    if foundOccurrences:
        for foundOccurrence in foundOccurrences:
            result[foundOccurrence.match] = foundOccurrence
            cache.globalCache.insert("occurrenceCacheMatch",foundOccurrence.match,foundOccurrence)
    return result
