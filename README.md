# jimiPlugin-occurrence

Enables alarm like functionality whereby it is possible for uniquue occurrences of events to only run a given part of the flow once while the alarm is in raised state. Alarm stste is determined by timers and counters. This measns that if an event is not seen for x time and the trigger is triggered x times within this window then the occurrence is cleared.

Occurrence supports 3 flow modes after the object hsa been placed:
1. Raise - A new occurence has been seen
data[action][rc] == 201
2. Update - A existing occurrence will be updated and time extended
data[action][rc] == 302
3. Clear - A occurrence has expired and is now cleared
data[action][rc] == 205

The RC codes shown above should be used within login in a jimiFlow to determine what parts of your flow should run in relation to the above outputs.

## Parameters
occurrenceMatchString - string - What makes this event uniquue - %%data[event][host]%%
lullTime - int - How long in seconds do we wait for the event to be seen again - 300
lullTimeExpiredCount - int - How many times does the trigger need to run after it has expired before it is cleared - 3

occurrenceMatchString uses jimi standard string replacement and can contain as many items as you like, they get joined together to make a match string which is then used to workout if this is the first time a given event has been seen.
