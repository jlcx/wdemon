cg_rels = {
    'P737': 'influenced by',
    'P941': 'inspired by',
    'P2675': 'reply to',
    'P144': 'based on',
    'P828': 'has cause',
    'P1542': 'cause of',
    'P1478': 'has immediate cause',
    'P1536': 'immediate cause of',
    'P1479': 'has contributing factor',
    'P1537': 'contributing factor of',
    'P22': 'father',
    'P25': 'mother',
    'P40': 'child',
    'P184': 'doctoral advisor',
    'P185': 'doctoral student',
    'P1066': 'student of',
    'P802': 'student',
    # 'P2860': 'cites', # I believe this dwarfs the combined count of others
    'P807': 'separated from',
    'P112': 'founded by',
    'P170': 'creator',
    'P50': 'author',
    'P61': 'discoverer or inventor',
    'P86': 'composer',
    'P87': 'librettist',
    'P178': 'developer',
    'P287': 'designed by',
    'P943': 'programmer',
    'P193': 'main building contractor',
    'P676': 'lyrics by',
    'P175': 'performer',
    'P84': 'architect',
    'P110': 'illustrator',
    'P1779': 'possible creator',
    'P5191': 'derived from',
    'P3448': 'stepparent',
    'P156': 'followed by',
    'P155': 'follows',
    'P1366': 'replaced by',
    'P1365': 'replaces',
    'P167': 'structure replaced by',
    'P710': 'participant',
    'P1344': 'participant of',
    'P162': 'producer',
    'P272': 'production company',
    'P2515': 'costume designer',
    'P4805': 'make-up artist',
    'P2554': 'production designer',
    'P1040': 'film editor',
    'P3092': 'film crew member',
    'P3342': 'significant person',
    'P344': 'director of photography',
    'P1431': 'executive producer',
    'P161': 'cast member',
    'P58': 'screenwriter',
    'P57': 'director',
    'P138': 'named after',
    'P800': 'notable work',
    'P3919': 'contributed to creative work',
    'P6338': 'colorist',
    'P176': 'manufacturer',
    'P8371': 'references work, tradition or theory',
    'P4969': 'derivative work',
    'P6166': 'quotes work',
    'P5707': 'samples from work',
    'P1625': 'has melody',
    'P6439': 'has lyrics',
    'P1877': 'after a work by',
    'P5059': 'modified version of',
    'P629': 'edition or translation of',
    'P9810': 'remix of',
    # 'P180': 'depicts', # potentially useful, but has potential issues
    # 'P1455': 'list of works', # include this?
    'P279': 'subclass of'  # different from the others, but we need this too
}


# TODO these may have nested date information, so look at them
nested_time_rels = {
    'P348': 'software version',
    'P106': 'occupation',
    'P108': 'employer',
    'P69': 'educated at',
    'P26': 'spouse',
    'P176': 'manufacturer',
    'P449': 'original network',
    'P793': 'significant event',
    'P1891': 'signatory'  # many US laws seem to have a date only here
}

# if a statement using one of these doesn't have a date on either end,
# then it's probably something like "ethanol cause of ethanol exposure",
# which isn't suitable for CauseGraph.  TODO: Filter that stuff.
likely_nonspecific = frozenset(
    ['P828', 'P1542', 'P1478', 'P1536', 'P1479', 'P1537'])

# these aren't that great, would need lots of filtering
# 'P509': 'cause of death', 'P770': 'cause of destruction',

# there's also P523 and P524 for 'temporal range' for e.g. dinosaurs

# TODO get subproperties for times below; you're still missing some
# TODO use earliest and latest when present with an unknown date

starts = {
    'P580': 'start time',
    'P571': 'inception',
    'P569': 'date of birth',
    'P575': 'time of discovery or invention',
    'P1191': 'first performance',
    'P577': 'publication date',
    'P2031': 'work period (start)',
    'P1619': 'date of official opening',
    'P1319': 'earliest date',
    'P729': 'service entry',
    'P606': 'first flight',
    'P1249': 'time of earliest written record',
    'P523': 'temporal range start'
}

ends = {
    'P582': 'end time',
    'P576': 'dissolved, abolished or demolished',
    'P570': 'date of death',
    'P2032': 'work period (end)',
    'P2669': 'discontinued date',
    'P1326': 'latest date',
    'P730': 'service retirement',
    'P3999': 'date of official closure',
    'P524': 'temporal range end'
}

others = {
    'P585': 'point in time',
    'P1317': 'floruit'
}

all_times = frozenset(list(starts.keys())
                      + list(ends.keys())
                      + list(others.keys()))

times_plus_nested = frozenset(list(starts.keys())
                              + list(ends.keys())
                              + list(others.keys())
                              + list(nested_time_rels.keys()))

# these inverse relationships are present in Wikidata
original_inverses = {
    'P22': 'P40',  # father/mother more specific
    'P25': 'P40',
    'P828': 'P1542',
    # 'P828': 'P1536',  # both listed as inverses? not sure it makes sense
    'P184': 'P185',
    'P1066': 'P802',
    'P1478': 'P1536',
    'P1479': 'P1537',
    'P155': 'P156',
    'P1365': 'P1366',
    'P710': 'P1344'
}

combined_inverses = {
    'P22': 'P40',  # "father of"
    'P25': 'P40',  # "mother of"
    'P3448': 'P3448i', # "stepparent of"
    'P737': 'P737i',  # "influenced"
    'P941': 'P941i',  # "inspired"
    'P2675': 'P2675i',  # "received reply"
    'P144': 'P4969',  # "basis of" or "derivative work"
    'P828': 'P1542',
    'P184': 'P185',
    'P1066': 'P802',
    'P1478': 'P1536',
    'P1479': 'P1537',
    'P155': 'P156',
    'P1365': 'P1366',
    'P50': 'P50i',  # "authored"
    'P943': 'P943i', # "programmed"
    'P86': 'P86i',
    'P170': 'P170i', # "created"
    'P1779': 'P1779i', # "possibly created"
    'P112': 'P112i',  # "founded"
    'P175': 'P175i',
    'P84': 'P84i',
    'P178': 'P178i',
    'P807': 'P807i',
    'P193': 'P193i',
    'P110': 'P110i',  # "illustrated"
    'P287': 'P287i',  # "designed"
    'P676': 'P676i',  # "wrote lyrics for"
    'P61': 'P61i',  # "discovered or invented"
    'P710': 'P1344',
    'P138': 'P138i',
    'P176': 'P176i',  # "manufacturer of"
    'P161': 'P161i',  # "cast member of"
    'P57':  'P57i',  # "directed"
    'P58': 'P58i',  # "wrote screenplay for"
    'P162': 'P162i',  # "produced"
    'P272': 'P272i',  # "produced (as a company)"
    'P344': 'P344i',  # "directed photography for"
    'P1040': 'P1040i',  # "did film editing for"
    'P2554': 'P2554i',  # "was production designer for"
    'P1431': 'P1431i',  # "was executive producer of"
    'P2515': 'P2515i',  # "designed costumes for"
    'P4805': 'P4805i',  # "make-up artist for"
    'P87': 'P87i',  # "was librettist for"
    'P3092': 'P3092i',  # "film crew member for"
    'P6338': 'P6338i',  # "colorist for"
    'P176': 'P176i',  # "manufactured"
    'P8371': 'P8371i',  # "work, tradition or theory referenced by"
    'P6166': 'P6166i',  # "quoted in"
    'P5707': 'P5707i',  # "sampled in"
    'P1625': 'P1625i',  # "melody used in"
    'P6439': 'P6439i',  # "lyrics used in"
    'P1877': 'P1877i',  # "after a work by" inverse
    'P5059': 'P5059i',
    'P629': 'P629i',
    'P9810': 'P9810i',  # "remixed into"
}

fictional_properties = ('P1074')

todo = [
    'Q735117',  # a reminder to use earliest/latest in the case of unknown date
]
