from flask import Blueprint, render_template
from flask import current_app as app

from pathlib import Path
import time

from core import api
from plugins.occurrence.models import occurrence

pluginPages = Blueprint('occurrencePages', __name__, template_folder="templates")

@pluginPages.route("/")
def mainPage():
    foundOccurrences = occurrence._occurrence().query(sessionData=api.g.sessionData)["results"]
    occurrences = []
    for foundOccurrence in foundOccurrences:
        o = {"_id" : "", "name" : "", "match" : "", "triggerID" : "", "occurrenceActionID" : "", "lastLullCheck" : 0, "occurrenceTime" : 0,  "lastOccurrenceTime" : 0, "data" : {}}
        o["_id"] = str(foundOccurrence["_id"])
        o["name"] = foundOccurrence["name"]
        o["match"] = foundOccurrence["match"]
        if "triggerID" in foundOccurrence:
            o["triggerID"] = foundOccurrence["triggerID"]
        if "occurrenceActionID" in foundOccurrence:
            o["occurrenceActionID"] = foundOccurrence["occurrenceActionID"]
        if "lastLullCheck" in foundOccurrence:
            o["lastLullCheck"] = time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(foundOccurrence["lastLullCheck"]))
        if "lastOccurrenceTime" in foundOccurrence:
            o["lastOccurrenceTime"] = time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(foundOccurrence["lastOccurrenceTime"]))
        if "data" in foundOccurrence:
            o["data"] = foundOccurrence["data"]
        if "occurrenceTime" in foundOccurrence:
            o["occurrenceTime"] = time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(foundOccurrence["occurrenceTime"]))
        if "lullTime" in foundOccurrence:
            o["lullTime"] = time.strftime('%d/%m/%Y %H:%M:%S', time.gmtime(foundOccurrence["lullTime"]))
        if "lullTimeExpired" in foundOccurrence:
            o["lullTimeExpired"] = foundOccurrence["lullTimeExpired"]

        occurrences.append(o)
    return render_template("occurrence.html", occurrences=occurrences)

@pluginPages.route("/<occurrenceID>/clear/")
def clearOccurrence(occurrenceID):
    foundOccurence =  occurrence._occurrence().query(sessionData=api.g.sessionData,id=occurrenceID)["results"]
    if len(foundOccurence) == 1:
        occurrence._occurrence().api_delete(id=occurrenceID)
        return {}, 200
    else:
        return (), 404