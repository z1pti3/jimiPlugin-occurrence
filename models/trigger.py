from core.models import trigger

class _raiseOccurrence(trigger._trigger):
    schedule = None
    enabled = True

class _updateOccurrence(trigger._trigger):
    schedule = None
    enabled = True

class _clearOccurrence(trigger._trigger):
    schedule = None
    enabled = True

