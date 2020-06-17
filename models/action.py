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
    raiseOccurrenceTriggerID = str()
    updateOccurrenceTriggerID = str()
    clearOccurrenceTriggerID = str()

    def __init__(self):
        # Used to cahce object loads and reduce database requests ( set to none some schema excludes them )
        self.raiseOccurrenceCache = None
        self.updateOccurrenceCache = None
        self.conductsCache = None
        cache.globalCache.newCache("occurrenceCache",maxSize=104857600)

    def new(self, name):
        # no longer create occurrence triggers result codes should be used instead!
        #self.raiseOccurrenceTriggerID = str(occurrenceTrigger._raiseOccurrence().new("{0} - raise".format(name)).inserted_id)
        #self.updateOccurrenceTriggerID = str(occurrenceTrigger._updateOccurrence().new("{0} - update".format(name)).inserted_id)
        #self.clearOccurrenceTriggerID = str(occurrenceTrigger._clearOccurrence().new("{0} - clear".format(name)).inserted_id)
        return super(_occurrence, self).new(name)

    def run(self,data,persistentData,actionResult):
        # Is this a clear event passed by the occurrence clear notifier?
        if "clearOccurrence" in data:
            actionResult["result"] = True
            actionResult["rc"] = 205
            return actionResult

        text = self._id
        if len(self.occurrenceMatchString) > 0:
            valueMatches = re.finditer(r'((\"(.*?[^\\])\"|([a-zA-Z0-9]+(\[(.*?)\])+)|([a-zA-Z0-9]+(\((.*?)(\)\)|\)))+)))',self.occurrenceMatchString)
            for index, valueMatch in enumerate(valueMatches, start=1):
                text += str(helpers.typeCast(valueMatch.group(1).strip(),{"data" : data},{}))
        else:
            for field in self.eventFieldGroup:
                if field in data["event"]:
                    text += str(data["event"][field])
        match = text
        # NEED TO UPDATE / INSERT, on all matches at once to reduce looping and database load, this needs to be more effenit
        # Check for existing occurrence matches
        foundOccurrences = cache.globalCache.get("occurrenceCache",match,getOccurrenceObject,extendCacheTime=True)
        if not foundOccurrences:
            # Raising new occurrence
            newOccurrence = occurrence._occurrence().new(self,match,helpers.unicodeEscapeDict(data))
            if newOccurrence:
                self.notifyConducts("raise",data)
                logging.debug("Occurrence Created, occurrenceID='{0}' actionID='{1}'".format(newOccurrence.inserted_id,self._id),7)
                actionResult["result"] = True
                actionResult["rc"] = 201
                return actionResult
            else:
                actionResult["result"] = False
                actionResult["rc"] = 500
                return actionResult
        else:
            # Updating existing occurrences
            for foundOccurrence in foundOccurrences:
                foundOccurrence.lastOccurrenceTime = int(time.time())
                foundOccurrence.lullTime = (foundOccurrence.lastOccurrenceTime + self.lullTime)
                foundOccurrence.lullTimeExpired = self.lullTimeExpiredCount
                foundOccurrence.update(["lastOccurrenceTime","lullTime","lullTimeExpired"])
                data["occurrenceData"] = foundOccurrence.data
                self.notifyConducts("update",data)
                logging.debug("Occurrence Updated, occurrenceID='{0}' actionID='{1}'".format(foundOccurrence._id,self._id),7)
                actionResult["result"] = True
                actionResult["rc"] = 302
                return actionResult
                    

    def notifyConducts(self,occurrenceTriggerType,data):
        # Old methord which fails when using new methord
        try:
            # Following simular speed and caching as scheduler loop
            
            triggerClass = None
            
            if occurrenceTriggerType == "raise":
                if not self.raiseOccurrenceCache:
                    self.raiseOccurrenceCache = occurrenceTrigger._raiseOccurrence().load(self.raiseOccurrenceTriggerID).parse(hidden=True)
                triggerClass = self.raiseOccurrenceCache
            elif occurrenceTriggerType == "update":
                if not self.updateOccurrenceCache:
                    self.updateOccurrenceCache = occurrenceTrigger._updateOccurrence().load(self.updateOccurrenceTriggerID).parse(hidden=True)
                triggerClass = self.updateOccurrenceCache
            
            if triggerClass != None:
                if triggerClass["enabled"]:
                    #data["triggerID"] = triggerClass["_id"]
                    if not self.conductsCache:
                        self.conductsCache = []
                        conducts = conduct._conduct().query(query={"flow.triggerID" : triggerClass["_id"], "enabled" : True})["results"]
                        for conduct_ in conducts:
                            # Dynamic loading for classType model
                            _class = model._model().get(conduct_["classID"]).classObject()
                            if _class:
                                self.conductsCache.append(_class().load(conduct_["_id"]))
                    for conduct_ in self.conductsCache:
                        conduct_.triggerHandler(triggerClass["_id"],data)
        except:
            pass

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

                

            conducts = foundOccurrenceCache[foundOccurrence["occurrenceActionID"]]["conducts"]
            data = { "triggerID" : "", "var" : {}, "event" : {} }
            # If occurrence contains the orgnial data var and event then apply it to the data passsed to clear
            if "data" in foundOccurrence:
                data["event"] = foundOccurrence["data"]["event"]
                data["var"] = foundOccurrence["data"]["var"]
            data["triggerID"] = foundOccurrenceCache[foundOccurrence["occurrenceActionID"]]["triggerID"]
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
                        loadedConduct.triggerHandler(triggerClass["_id"],data)
                    except:
                        pass # Error handling is needed here

            # New exit code version
            conducts = foundOccurrenceCache[foundOccurrence["occurrenceActionID"]]["exitCodeMode"]["conducts"]
            data = { "triggerID" : "", "clearOccurrence" : True, "var" : {}, "event" : {} }
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
                        loadedConduct.triggerHandler(tempOccurrence._id,data,True)
                    except:
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
    return occurrence._occurrence().getAsClass(query={"match" : match })