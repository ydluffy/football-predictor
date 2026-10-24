"""Conservative cross-provider candidates. Names alone never approve a binding."""
import unicodedata


def words(value):
    text = unicodedata.normalize("NFKD", value or "").casefold()
    return "".join(c if c.isalnum() else " " for c in text if not unicodedata.combining(c)).split()


def compatible_name(local, external):
    left, right = words(local), words(external)
    if not left or not right:
        return False
    if left == right:
        return True
    # Only an initial plus the complete remaining surname, not fuzzy edit distance.
    return len(left) == len(right) and all(a == b or (len(a) == 1 and b.startswith(a)) for a,b in zip(left,right))


def classify(name, profile, external):
    observations = external["observations"]
    names = {name, profile.get("name")}
    if profile.get("firstname") and profile.get("lastname"):
        names.add(profile["firstname"] + " " + profile["lastname"])
    if not observations or not any(compatible_name(n, o["profile"].get("name")) for n in names for o in observations):
        return None
    birth = (profile.get("birth") or {}).get("date")
    dates = {o["profile"].get("dateOfBirth") for o in observations}
    if len(dates) != 1:
        return "source_birth_conflict"
    if not birth:
        return "name_only_needs_birth"
    if birth not in dates:
        return "birth_conflict"
    return "name_and_birth_agree"
