import uuid

from core import db, logging, plugin, model
from core.models import conduct, trigger, webui

from plugins.occurrence.models import action

class _occurrence(plugin._plugin):
    version = 3.1

    def install(self):
        # Register models
        model.registerModel("occurrence","_occurrence","_action","plugins.occurrence.models.action")
        model.registerModel("occurrence clean","_occurrenceClean","_action","plugins.occurrence.models.action")
        model.registerModel("occurrence raise","_raiseOccurrence","_trigger","plugins.occurrence.models.trigger")
        model.registerModel("occurrence update","_updateOccurrence","_trigger","plugins.occurrence.models.trigger")
        model.registerModel("occurrence clear","_clearOccurrence","_trigger","plugins.occurrence.models.trigger")

        # Finding conduct
        foundConducts = conduct._conduct().query(query={"name" : "occurrenceCore"  })["results"]
        if len(foundConducts) == 0:
            # Install
            c = conduct._conduct().new("occurrenceCore")
            c = conduct._conduct().get(c.inserted_id)
        elif len(foundConducts) == 1:
            # Reinstall
            c = conduct._conduct().get(foundConducts[0]["_id"])
        else:
            # Count invalid
            return False

        # Finding trigger
        foundTriggers = trigger._trigger().query(query={"name" : "occurrenceCore"  })["results"]
        if len(foundTriggers) == 0:
            # Install
            t = trigger._trigger().new("occurrenceCore")
            t = trigger._trigger().get(t.inserted_id)
        elif len(foundTriggers) == 1:
            # Reinstall
            t = trigger._trigger().get(foundTriggers[0]["_id"])
        else:
            # Count invalid
            return False

        # Finding action
        foundActions = action._occurrenceClean().query(query={"name" : "occurrenceCore"  })["results"]
        if len(foundActions) == 0:
            # Install
            a = action._occurrenceClean().new("occurrenceCore")
            a = action._occurrenceClean().get(a.inserted_id)
        elif len(foundActions) == 1:
            # Reinstall
            a = action._occurrenceClean().get(foundActions[0]["_id"])
        else:
            # Count invalid
            return False

        c.triggers = [t._id]
        flowTriggerID = str(uuid.uuid4())
        flowActionID = str(uuid.uuid4())
        c.flow = [
            {
                "flowID" : flowTriggerID,
                "type" : "trigger",
                "triggerID" : t._id,
                "next" : [
                    {"flowID": flowActionID, "logic": True }
                ]
            },
            {
                "flowID" : flowActionID,
                "type" : "action",
                "actionID" : a._id,
                "next" : []
            }
        ]
        webui._modelUI().new(c._id,{ "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] },flowTriggerID,0,0,"")
        webui._modelUI().new(c._id,{ "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] },flowActionID,100,0,"")

        c.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
        c.enabled = True
        c.update(["triggers","flow","enabled","acl"])

        t.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
        t.schedule = "60-90s"
        t.enabled = True
        t.update(["schedule","enabled","acl"])

        a.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
        a.enabled = True
        a.update(["enabled","acl"])

        # Hide Created Models
        temp = model._model().getAsClass(query={ "name" : "occurrence clean" })
        if len(temp) == 1:
            temp = temp[0]
            temp.hidden = True
            temp.update(["hidden"])
        temp = model._model().getAsClass(query={ "name" : "occurrence raise" })
        if len(temp) == 1:
            temp = temp[0]
            temp.hidden = True
            temp.update(["hidden"])
        temp = model._model().getAsClass(query={ "name" : "occurrence update" })
        if len(temp) == 1:
            temp = temp[0]
            temp.hidden = True
            temp.update(["hidden"])
        temp = model._model().getAsClass(query={ "name" : "occurrence clear" })
        if len(temp) == 1:
            temp = temp[0]
            temp.hidden = True
            temp.update(["hidden"])

        return True

    def uninstall(self):
        # deregister models
        model.deregisterModel("occurrence","_occurrence","_action","plugins.occurrence.models.action")
        model.deregisterModel("occurrence clean","_occurrenceClean","_action","plugins.occurrence.models.action")
        model.deregisterModel("occurrence raise","_raiseOccurrence","_trigger","plugins.occurrence.models.trigger")
        model.deregisterModel("occurrence update","_updateOccurrence","_trigger","plugins.occurrence.models.trigger")
        model.deregisterModel("occurrence clear","_clearOccurrence","_trigger","plugins.occurrence.models.trigger")
        
        conduct._conduct().api_delete(query={"name" : "occurrenceCore"  })
        trigger._trigger().api_delete(query={"name" : "occurrenceCore"  })
        action._occurrenceClean().api_delete(query={"name" : "occurrenceCore"  })
        return True

    def upgrade(self,LatestPluginVersion):
        if self.version < 3.1:
            temp = conduct._conduct().getAsClass(query={"name" : "occurrenceCore"  })
            if len(temp) == 1:
                temp = temp[0]
                temp.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
                temp.flow[0]["next"] = [{"flowID": temp.flow[1]["flowID"], "logic": True }]
                temp.update(["flow","acl"])
                webui._modelUI().new(temp._id,{ "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] },temp.flow[0]["flowID"],0,0,"")
                webui._modelUI().new(temp._id,{ "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] },temp.flow[1]["flowID"],250,0,"")
            temp = model._model().getAsClass(query={ "name" : "occurrence clean" })
            if len(temp) == 1:
                temp = temp[0]
                temp.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
                temp.update(["acl"])
            temp = model._model().getAsClass(query={ "name" : "occurrence raise" })
            if len(temp) == 1:
                temp = temp[0]
                temp.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
                temp.update(["acl"])
            temp = model._model().getAsClass(query={ "name" : "occurrence update" })
            if len(temp) == 1:
                temp = temp[0]
                temp.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
                temp.update(["acl"])
            temp = model._model().getAsClass(query={ "name" : "occurrence clear" })
            if len(temp) == 1:
                temp = temp[0]
                temp.acl = { "ids":[ { "accessID":"0","delete": True,"read": True,"write": True } ] }
                temp.update(["acl"])

        # Hiding object types
        if self.version < 2:
            temp = model._model().getAsClass(query={ "name" : "occurrence clean" })
            if len(temp) == 1:
                temp = temp[0]
                temp.hidden = True
                temp.update(["hidden"])
            temp = model._model().getAsClass(query={ "name" : "occurrence raise" })
            if len(temp) == 1:
                temp = temp[0]
                temp.hidden = True
                temp.update(["hidden"])
            temp = model._model().getAsClass(query={ "name" : "occurrence update" })
            if len(temp) == 1:
                temp = temp[0]
                temp.hidden = True
                temp.update(["hidden"])
            temp = model._model().getAsClass(query={ "name" : "occurrence clear" })
            if len(temp) == 1:
                temp = temp[0]
                temp.hidden = True
                temp.update(["hidden"])

        return True
    