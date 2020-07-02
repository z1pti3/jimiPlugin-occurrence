import time

from core import db, helpers, logging

# Initialize

dbCollectionName = "occurrence"

if dbCollectionName not in db.db.list_collection_names():
    logging.debug("DB Collection {0} Not Found : Creating...".format(dbCollectionName))

class _occurrence(db._document):
    name = str()
    lullTime = int()
    match = str()
    occurrenceTime = int()
    lastOccurrenceTime = int()
    occurrenceActionID = str()
    lullTimeExpired = int()
    lastLullCheck = int()
    triggerID = str()
    data = dict()

    _dbCollection = db.db[dbCollectionName]

    def asyncNew(self,occurrenceObj,match,data,acl):
        self.acl = acl
        self.name = occurrenceObj.name
        self.match = match
        self.occurrenceTime = int(time.time())
        self.lullTime = (self.occurrenceTime + occurrenceObj.lullTime)
        self.occurrenceActionID = occurrenceObj._id
        self.lullTimeExpired = occurrenceObj.lullTimeExpiredCount
        if "callingTriggerID" in data:
            if data["callingTriggerID"] != "":
                self.triggerID = data["callingTriggerID"]
            else:
                logging.debug("Error using callingTriggerID as it is blank")
                self.triggerID = data["triggerID"]
        else:
            self.triggerID = data["triggerID"]
        if self.triggerID == "":
            return None
        self.data = data
        self.lastLullCheck = int(time.time())
        return super(_occurrence, self).asyncNew() 

# Locates occurrences by match field
def findOccurrences(match):
    result = []
    foundOccurrences = _occurrence().query(query={"match" : match })["results"]
    for foundOccurrence in foundOccurrences:
        if foundOccurrence is not None:
            result.append(_occurrence().get(foundOccurrence["_id"]))
    return result

