import hashlib
import time
import re

from core import logging, helpers, db, workers, model, cache
from core.models import action, conduct, trigger

from plugins.occurrence.models import occurrence
from plugins.occurrence.models import trigger as occurrenceTrigger

# Needs to be updated so that objects are cahced and then mass updated into the database on class __del__

class _occurrence(action._action):
    eventFieldGroup = list()
    occurrenceMatchString = str()
    lullTime = int()
    lullTimeExpiredCount = int()

    def __init__(self):
        # Used to cahce object loads and reduce database requests ( set to none some schema excludes them )
        cache.globalCache.newCache("occurrenceCache",maxSize=104857600)
        cache.globalCache.get("occurrenceCache","all",getOccurrenceObjects)
        cache.globalCache.newCache("occurrenceCacheMatch",maxSize=104857600)
        self.cpuSaver = helpers.cpuSaver()

    def run(self,data,persistentData,actionResult):
        # force CPU down as this action can afford to take a few seconds 1 sec delay per 1000 events
        self.cpuSaver.tick(runAfter=100,sleepFor=0.1)
        # Is this a clear event passed by the occurrence clear notifier?
        if "clearOccurrence" in data:
            actionResult["result"] = True
            actionResult["rc"] = 205
            return actionResult

        match = "{0}-{1}".format(self._id,helpers.evalString(self.occurrenceMatchString,{ "data" : data }))
        # Check for existing occurrence matches
        foundOccurrence = cache.globalCache.get("occurrenceCacheMatch",match,getOccurrenceObject,dontCheck=True)
        if foundOccurrence == None:
            # Raising new occurrence and assuming the database took the object as expected
            newOccurrence = occurrence._occurrence().asyncNew(self,match,helpers.unicodeEscapeDict(data),self.acl)
            cache.globalCache.insert("occurrenceCacheMatch",match,newOccurrence)
            logging.debug("Occurrence Created async, actionID='{0}'".format(self._id),7)
            actionResult["result"] = True
            actionResult["rc"] = 201
            return actionResult
        else:
            if foundOccurrence._id != "":
                # Updating existing occurrences
                foundOccurrence.lastOccurrenceTime = int(time.time())
                foundOccurrence.lullTime = (foundOccurrence.lastOccurrenceTime + self.lullTime)
                foundOccurrence.lullTimeExpired = self.lullTimeExpiredCount
                foundOccurrence.asyncUpdate(["lastOccurrenceTime","lullTime","lullTimeExpired"])
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
            if foundOccurrence["occurrenceActionID"] not in foundOccurrenceCache:
                # Old methord now fails when using new methord
                tempOccurrence = _occurrence().load(foundOccurrence["occurrenceActionID"])
                try:
                    triggerClass = occurrenceTrigger._clearOccurrence().load(tempOccurrence.clearOccurrenceTriggerID).parse(hidden=True)
                    
                    # Checking if clear trigger is enabled
                    if triggerClass["enabled"]:
                        conducts = conduct._conduct().query(query={"flow.triggerID" : triggerClass["_id"], "enabled" : True})["results"]
                        foundOccurrenceCache[foundOccurrence["occurrenceActionID"]] = { "triggerID": triggerClass["_id"], "conducts" : conducts }
                    else:
                        # Save blank list of conducts if the clear tigger is disabled
                        foundOccurrenceCache[foundOccurrence["occurrenceActionID"]] = { "triggerID": triggerClass["_id"], "conducts" : [] }
                except:
                     foundOccurrenceCache[foundOccurrence["occurrenceActionID"]] = { "triggerID": None, "conducts" : [] }

                # New exit code version
                if tempOccurrence.enabled:
                    conducts = conduct._conduct().query(query={"flow.actionID" : tempOccurrence._id, "enabled" : True})["results"]
                    foundOccurrenceCache[foundOccurrence["occurrenceActionID"]]["exitCodeMode"] = { "actionID": tempOccurrence._id, "conducts" : conducts }

            # New exit code version
            conducts = foundOccurrenceCache[foundOccurrence["occurrenceActionID"]]["exitCodeMode"]["conducts"]
            data = { "triggerID" : tempOccurrence._id, "clearOccurrence" : True, "var" : {}, "event" : {} }
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
                        logging.debug("Cannot locate occurrence by ID, occurrenceID='{0}'".format(occurrenceID),6)
                else:
                    loadedConduct = conductsCache[conduct_["classID"]]

                if loadedConduct:
                    try:
                        loadedConduct.triggerHandler(tempOccurrence._id,data,actionIDType=True)
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
    for foundOccurrence in foundOccurrences:
        result[foundOccurrence.match] = foundOccurrence
        cache.globalCache.insert("occurrenceCacheMatch",foundOccurrence.match,foundOccurrence)
    return result
