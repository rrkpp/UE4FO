import sys
import struct
import os
import math

SETTINGS = {
	'dumpgroups' : False,
	'nomanifests' : False,
	'allsubs' : False,
	'scale' : 1.4
}

# This will be our topmost data structure to hold the
# parsed contents of each .ESM top group
GRUPS = {
	'CELL' : {'interior' : {}, 'exterior' : {}},
	'STAT' : {},
	'CONT' : {},
	'FURN' : {},
	'DOOR' : {},
	'AMMO' : {},
	'ACTI' : {},
	'ALCH' : {},
	'ARMO' : {},
	'BOOK' : {},
	'KEYM' : {},
	'MISC' : {},
	'WEAP' : {},
}

# Parses a generic record. Doesn't work for some like REFR because REFR is semi-special
# in that it describes a reference to an actual record. Other records are much
# more similar and thus can be handled by the generic parseRecord.
# f = .ESM file handle
# rtype = Record Type
def parseRecord(f, rtype):
	# Parse record header
	size = struct.unpack('<L', f.read(4))[0]
	flags = struct.unpack('<L', f.read(4))[0]
	formid = struct.unpack('<L', f.read(4))[0]
	vcontrol = struct.unpack('<L', f.read(4))[0]
	formvs = struct.unpack('<H', f.read(2))[0]
	vcontrol2 = struct.unpack('<h', f.read(2))[0]

	# Get the first subrecord name and create our result dict
	subName = f.read(4).decode()
	result = {}

	# Break loop when we get to the next record or top group
	while subName != rtype and subName != 'GRUP':
		subSize = struct.unpack('<H', f.read(2))[0]
		subData = f.read(subSize)

		if subName == 'EDID': # Editor ID
			result['EDID'] = subData.decode('utf-8', 'ignore').replace('\x00', '')

		if subName == 'FULL': # Full name
			result['FULL'] = subData.decode('utf-8', 'ignore').replace('\x00', '')

		if subName == 'MODL': # Model filename
			result['MODL'] = subData.decode('utf-8', 'ignore').replace('\x00', '').replace('\\', '/')

		# Parse object-specific subrecords
		if rtype == 'CONT': # Container
			result['CNTO'] = {}
			while subName == 'CNTO': # Object list
				obFormId = struct.unpack('<L', subData[:4])[0]
				obCount = struct.unpack('<L', subData[4:9])[0]
				result['CNTO'][obFormId] = obCount

				# Load the next subrecord, if it's more container objects
				# the loop will parse it, otherwise the loop will exit and
				# normal parsing will continue
				subName = f.read(4).decode()
				subSize = struct.unpack('<H', f.read(2))[0]
				subData = f.read(subSize)

			if subName == 'SNAM': # Open sound
				result['SNAM'] = struct.unpack('<L', subData)[0]
			if subName == 'QNAM': # Close sound
				result['QNAM'] = struct.unpack('<L', subData)[0]

		subName = f.read(4).decode() # Read the next subrecord name

	GRUPS[rtype][formid] = result
	f.seek(f.tell() - 4) # Seek back to the beginning of next record (compensates for next subrecord seek in while loop)

def parseREFR(f):
	size = struct.unpack('<L', f.read(4))[0]
	flags = struct.unpack('<L', f.read(4))[0]
	formid = struct.unpack('<L', f.read(4))[0]
	vcontrol = struct.unpack('<L', f.read(4))[0]
	formvs = struct.unpack('<H', f.read(2))[0]
	vcontrol2 = struct.unpack('<h', f.read(2))[0]

	subName = f.read(4).decode()
	result = {}
	
	while subName != 'REFR' and subName != 'GRUP' and subName != 'ACHR' and subName != 'CELL' and subName != 'ACRE' and subName != 'PGRE':
		subSize = struct.unpack('<H', f.read(2))[0]
		subData = f.read(subSize)

		if subName == 'NAME': # FormID of referenced object
			result['NAME'] = struct.unpack('<L', subData)[0]
		elif subName == 'DATA': # Location/Rotation data
			xpos = struct.unpack('<f', subData[:4])[0]
			ypos = -struct.unpack('<f', subData[4:8])[0]
			zpos = struct.unpack('<f', subData[8:12])[0]
			radX = round(struct.unpack('<f', subData[12:16])[0], 5)
			radY = round(struct.unpack('<f', subData[16:20])[0], 5)
			radZ = round(struct.unpack('<f', subData[20:24])[0], 5)
			degX = math.degrees(radX) #((math.degrees(radX) + 180) % 360)
			degY = math.degrees(radY) #((math.degrees(radY) + 180) % 360)
			degZ = math.degrees(radZ) + 180 #((math.degrees(radZ) + 180) % 360)

			result['DATA'] = [xpos * SETTINGS['scale'], ypos * SETTINGS['scale'], zpos * SETTINGS['scale'], degY, degZ, degX]
			result['XSCL'] = SETTINGS['scale'];
			#result['DATA'] = [xpos, ypos, zpos, -round(math.degrees(radY)), -round(math.degrees(radZ)), -round(math.degrees(radX))]
		elif subName == 'XSCL': # Scale (Only present if != 1.0)
			result['XSCL'] = struct.unpack('<f', subData)[0] * SETTINGS['scale']
		elif subName == 'ONAM': # Open by Default (Only for doors)
			result['ONAM'] = True
		elif SETTINGS['allsubs']:
			print('Unknown REFR subrecord ' + subName + ' with data: ' + subData.decode('utf-8', 'ignore'))

		subName = f.read(4).decode()

	f.seek(f.tell() - 4)
	return result

# This is for 'special' record types like REFR or ACHR
# which cannot be properly parsed by the generic
# parseRecord method.
parseFuncs = {}
parseFuncs['REFR'] = parseREFR

# Parses a group. This method calls itself numerous times to parse
# groups stored within groups and handle the different types of groups
# therein.
# Assumes the calling method did not seek back to the beginning of
# record and we are currently at the position of the size data.
def parseGroup(f):
	# Header data
	size = struct.unpack('<L', f.read(4))[0]
	label = f.read(4) # Needs to be decoded based on groupType
	groupType = struct.unpack('<l', f.read(4))[0]
	timestamp = struct.unpack('<L', f.read(4))[0]

	# This is only actually needed for certain group types,
	# in many cases the result will automatically be stored
	# in the appropriate GRUPS dict entry and thus the return
	# value will simply be a courtesy to the calling method.
	result = {}

	if groupType == 0: # Top Level Group
		groupName = label.decode()
		if groupName == 'CELL': # CELL top group holds all CELL records
			print('Parsing CELL group of size ' + str(size) + '..')
			f.seek(f.tell() + 16) # Skip to the group type for next group
			nextType = struct.unpack('<l', f.read(4))[0]
			f.seek(f.tell() - 12) # Seek back to the address of the group size

			blockNum = 0

			while nextType == 2: # Loop through Interior Cell Blocks
				GRUPS['CELL']['interior'][blockNum] = parseGroup(f) # Parse this block group

				f.seek(f.tell() + 12) # Skip to the group type for next group
				nextType = struct.unpack('<l', f.read(4))[0]
				f.seek(f.tell() - 12) # Seek back to the address of the group size

				blockNum += 1

			# TODO: Add parsing support for Exterior Cell Blocks

			f.seek(f.tell() - 4) # Seek back to the name of the next record
			return GRUPS['CELL'] # Return to avoid the f.seek() call at the bottom of this function
		elif groupName in GRUPS: # If group type is supported/parsable/relevant
			print('Parsing ' + groupName + ' group of size ' + str(size) + '..')
			f.seek(f.tell() + 4) # Seek past 4 magic bytes in group header
			
			nextType = f.read(4).decode() # Peek the next record type
			while nextType == groupName: # Loop through all STAT records
				parseRecord(f, nextType)
				nextType = f.read(4).decode()

			f.seek(f.tell() - 4) # Seek back to the start of the next record
			return GRUPS[groupName]
		else:
			print('Skipping top group ' + groupName + ' of size ' + str(size) + '..')
	elif groupType == 2: # Interior Cell Block
		blockNum = struct.unpack('<l', label)[0]
		print('Parsing Block ' + str(blockNum) + ' of size ' + str(size))

		f.seek(f.tell() + 16) # Skip to the group type for next group
		nextType = struct.unpack('<l', f.read(4))[0]
		f.seek(f.tell() - 12) # Seek back to the address of the group size

		subblock = 0

		while nextType == 3: # If the next group is an Interior Cell Block
			result[subblock] = {}
			result[subblock] = parseGroup(f)

			f.seek(f.tell() + 12) # Skip to the group type for next group
			nextType = struct.unpack('<l', f.read(4))[0]
			f.seek(f.tell() - 12) # Seek back to the address of the group size

			subblock += 1

		f.seek(f.tell() - 4) # Seek back to the name of the next record
		return result
	elif groupType == 3: # Interior Cell Sub Block
		subNum = struct.unpack('<l', label)[0]
		#print('Parsing Sub-Block ' + str(subNum) + ' of size ' + str(size))

		f.seek(f.tell() + 4) # Seek past 4 magic bytes of group header
		nextType = f.read(4).decode() # Peek the type of the next record

		cellNum = 0

		while nextType == 'CELL': # Loop through all CELL records
			result[cellNum] = {}
			result[cellNum] = parseCell(f)

			nextType = f.read(4).decode()
			cellNum += 1

		f.seek(f.tell() - 4) # Seek back to the name of the next record
		return result
	elif groupType == 6: # Cell Children
		f.seek(f.tell() + 16) # Seek to next group type
		nextType = struct.unpack('<l', f.read(4))[0]
		f.seek(f.tell() - 12) # Seek back to next group size
		
		# We're looking for two types of groups, Persistent and
		# Temporary cell children. Loop through the groups we find
		# and once we hit a group that isn't of the correct type,
		# we know we've hit the end of our cell.
		while nextType == 8 or nextType == 9:
			if nextType == 8:
				result['persistent'] = parseGroup(f)
			elif nextType == 9:
				result['temporary'] = parseGroup(f)

			f.seek(f.tell() + 12) # Seek to next group type
			nextType = struct.unpack('<l', f.read(4))[0]
			f.seek(f.tell() - 12) # Seek back to next group size

		f.seek(f.tell() - 4) # Seek back to next record name
		return result
	elif groupType == 8 or groupType == 9 : # Persistent/Temporary Cell Children
		f.seek(f.tell() + 4) # Seek to next record type
		childType = f.read(4).decode()
		result = []
		
		while True: # Loop through all cell child records
			if childType == 'GRUP' or childType == 'CELL': # If we run out of children..
				break

			if childType in parseFuncs: # If the child is parsable/relevant
				result.append(parseFuncs[childType](f))
			else:
				skipRecord(f)
		
			childType = f.read(4).decode() # Read next child record type
		
		f.seek(f.tell() - 4) # Seek back to start of next record
		return result
	else:
		print('Unknown group of size ' + str(size) + ' and type ' + str(groupType) + '!')
	
	f.seek(f.tell() + size - 20) # Seek to start of next record
	return result

# Parses a cell.
# Assumes the calling method did not seek back to the beginning of
# record and we are currently at the position of the size data.
def parseCell(f):
	result = {}

	# We don't necessarily want to parse everything about the cell,
	# so instead we will parse what we want, then use the cell start
	# address as a marker point so we know where we started and thus
	# how far to seek in order to get to the next record when we
	# exit the method.
	cellStartAddr = f.tell() - 4

	# Header data
	size = struct.unpack('<L', f.read(4))[0]
	flags = struct.unpack('<L', f.read(4))[0]
	formid = struct.unpack('<L', f.read(4))[0]
	vcontrol = struct.unpack('<l', f.read(4))[0]
	formvs = struct.unpack('<H', f.read(2))[0]
	vcontrol2 = struct.unpack('<h', f.read(2))[0]
	
	f.seek(f.tell() + 4) # Skip to the EDID size
	EDIDSize = struct.unpack('<H', f.read(2))[0]
	EDIDName = f.read(EDIDSize).decode().replace('\x00', '')
	
	f.seek(f.tell() + 4) # Skip to the FULL size
	fullNameSize = struct.unpack('<H', f.read(2))[0]
	fullName = f.read(fullNameSize).decode().replace('\x00', '')

	result['FormID'] = formid
	result['EDID'] = EDIDName
	f.seek(cellStartAddr + size + 24) # Seek to the start of the next record
	
	nextName = f.read(4).decode() # Peek the next record type and parse if GRUP
	if nextName == 'GRUP':
		result['Children'] = {}
		result['Children'] = parseGroup(f)
		return result
	
	f.seek(f.tell() - 4) # Seek back to start of the next record if we didn't find a GRUP
	return result

# Skips over a record and seeks to the start of the next one.
# Assumes the calling method did not seek back to the beginning of
# record and we are currently at the position of the size data.
def skipRecord(f):
	size = struct.unpack('<L', f.read(4))[0]
	f.seek(f.tell() + size + 16) # Seek past data + remainder of header

# Initiates the parsing of the supplied .ESM file
def parseESM(filepath):
	f = open(filepath, 'rb')
	try:
		while True:
			# Read the next record
			name = f.read(4).decode()
			
			if name == 'GRUP':
				parseGroup(f)
			elif name != '': # The only top level records are irrelevant to us, so skip them
				skipRecord(f)
			else:
				print("Finished parsing file.")
				break

	finally:
		f.close()

# Dumps top groups (not including CELL group) into
# .txt files. Moslty a debug utility.
def writeObjectsToFile():
	if not os.path.exists('topgroups/'):
		os.makedirs('topgroups/')

	for rtype, data in GRUPS.items():
		if rtype != 'CELL': # Cell output is handled in generateCellManifests()
			print('Dumping ' + rtype + ' group to file..')

			f = open('topgroups/' + rtype + '.txt', 'w+')
			f.write(str(data))
			f.close()

# Loops through all cells and generates
# UE4 importable .T3D files
def generateCellManifests():
	print('Generating cell manifests..')
	#if not os.path.exists('cells/'):
	#	os.makedirs('cells/')

	for zoneName, zone in GRUPS['CELL'].items():
		for blockNum, block in zone.items():
			for subNum, sub in block.items():
				for cellIndex, cell in sub.items():
					generateT3D(cell, 'cells/' + str(blockNum) + '/' + str(subNum) + '/')

# Generates a single .T3D file given a cell and
# an optional output directory for the .T3D file
# (The output directory is intended mostly for debug use)
def generateT3D(cell, directory=''):
	if directory != '' and not os.path.exists(directory):
		os.makedirs(directory)

	# Open our .T3D file and output the "header" for the map
	f = open(directory + cell['EDID'] + '.t3d', 'w+')
	f.write("""Begin Map Name=/Game/Maps/""" + cell['EDID'] + """
Begin Level NAME=PersistentLevel
   Begin Actor Class=WorldSettings Name=WorldSettings Archetype=WorldSettings'/Script/Engine.Default__WorldSettings'
      Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__WorldSettings:StaticMeshComponent0'
      End Object
      Begin Object Name="StaticMeshComponent0"
      End Object
      RootComponent=StaticMeshComponent0
      ActorLabel="WorldSettings-1"
   End Actor
   Begin Actor Class=Brush Name=Brush_5 Archetype=Brush'/Script/Engine.Default__Brush'
      Begin Object Class=BrushComponent Name="BrushComponent0" Archetype=BrushComponent'/Script/Engine.Default__Brush:BrushComponent0'
      End Object
      Begin Object Name="BrushComponent0"
         Brush=Model'"NewWorld:PersistentLevel.Brush"'
      End Object
      bNotForClientOrServer=True
      Begin Brush Name=Brush
         Begin PolyList
            Begin Polygon
               Origin   -00128.000000,-00128.000000,-00128.000000
               Normal   -00001.000000,+00000.000000,+00000.000000
               TextureU +00000.000000,+00001.000000,+00000.000000
               TextureV +00000.000000,+00000.000000,-00001.000000
               Vertex   -00128.000000,-00128.000000,-00128.000000
               Vertex   -00128.000000,-00128.000000,+00128.000000
               Vertex   -00128.000000,+00128.000000,+00128.000000
               Vertex   -00128.000000,+00128.000000,-00128.000000
            End Polygon
            Begin Polygon
               Origin   -00128.000000,+00128.000000,-00128.000000
               Normal   +00000.000000,+00001.000000,+00000.000000
               TextureU +00001.000000,-00000.000000,+00000.000000
               TextureV +00000.000000,+00000.000000,-00001.000000
               Vertex   -00128.000000,+00128.000000,-00128.000000
               Vertex   -00128.000000,+00128.000000,+00128.000000
               Vertex   +00128.000000,+00128.000000,+00128.000000
               Vertex   +00128.000000,+00128.000000,-00128.000000
            End Polygon
            Begin Polygon
               Origin   +00128.000000,+00128.000000,-00128.000000
               Normal   +00001.000000,+00000.000000,+00000.000000
               TextureU +00000.000000,-00001.000000,+00000.000000
               TextureV +00000.000000,+00000.000000,-00001.000000
               Vertex   +00128.000000,+00128.000000,-00128.000000
               Vertex   +00128.000000,+00128.000000,+00128.000000
               Vertex   +00128.000000,-00128.000000,+00128.000000
               Vertex   +00128.000000,-00128.000000,-00128.000000
            End Polygon
            Begin Polygon
               Origin   +00128.000000,-00128.000000,-00128.000000
               Normal   +00000.000000,-00001.000000,+00000.000000
               TextureU -00001.000000,-00000.000000,-00000.000000
               TextureV +00000.000000,+00000.000000,-00001.000000
               Vertex   +00128.000000,-00128.000000,-00128.000000
               Vertex   +00128.000000,-00128.000000,+00128.000000
               Vertex   -00128.000000,-00128.000000,+00128.000000
               Vertex   -00128.000000,-00128.000000,-00128.000000
            End Polygon
            Begin Polygon
               Origin   -00128.000000,+00128.000000,+00128.000000
               Normal   +00000.000000,+00000.000000,+00001.000000
               TextureU +00001.000000,+00000.000000,+00000.000000
               TextureV +00000.000000,+00001.000000,+00000.000000
               Vertex   -00128.000000,+00128.000000,+00128.000000
               Vertex   -00128.000000,-00128.000000,+00128.000000
               Vertex   +00128.000000,-00128.000000,+00128.000000
               Vertex   +00128.000000,+00128.000000,+00128.000000
            End Polygon
            Begin Polygon
               Origin   -00128.000000,-00128.000000,-00128.000000
               Normal   +00000.000000,+00000.000000,-00001.000000
               TextureU +00001.000000,+00000.000000,+00000.000000
               TextureV +00000.000000,-00001.000000,+00000.000000
               Vertex   -00128.000000,-00128.000000,-00128.000000
               Vertex   -00128.000000,+00128.000000,-00128.000000
               Vertex   +00128.000000,+00128.000000,-00128.000000
               Vertex   +00128.000000,-00128.000000,-00128.000000
            End Polygon
         End PolyList
      End Brush
      Brush=Model'Brush'
      BrushComponent=BrushComponent0
      bHidden=False
      RootComponent=BrushComponent0
      ActorLabel="Brush5"
   End Actor""")

	# Loop through children of the cell and write in the
	# appropriate UE4 actor data to the map
	if 'Children' in cell:
		for zoneName, zone in cell['Children'].items():
			for child in zone:
				for groupName, group in GRUPS.items():
					if child['NAME'] in group and groupName in writeRecToT3DFuncs:
						writeRecToT3DFuncs[groupName](f, child)

	# Wrap up the .T3D file
	f.write("""   End Level
Begin Surface
End Surface
End Map""")
	f.close()

# Static Meshes
def writeRecToT3D_STAT(f, record):
	if 'MODL' in GRUPS['STAT'][record['NAME']]:
		model = GRUPS['STAT'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['STAT'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['STAT'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Doors
def writeRecToT3D_DOOR(f, record):
	if 'MODL' in GRUPS['DOOR'][record['NAME']]:
		model = GRUPS['DOOR'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['DOOR'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['DOOR'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Furniture
def writeRecToT3D_FURN(f, record):
	if 'MODL' in GRUPS['FURN'][record['NAME']]:
		model = GRUPS['FURN'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['FURN'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['FURN'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Containers
def writeRecToT3D_CONT(f, record):
	if 'MODL' in GRUPS['CONT'][record['NAME']]:
		model = GRUPS['CONT'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['CONT'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['CONT'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Ammo
def writeRecToT3D_AMMO(f, record):
	if 'MODL' in GRUPS['AMMO'][record['NAME']]:
		model = GRUPS['AMMO'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['AMMO'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['AMMO'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Activator
def writeRecToT3D_ACTI(f, record):
	if 'MODL' in GRUPS['ACTI'][record['NAME']]:
		model = GRUPS['ACTI'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']
		
		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['ACTI'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['ACTI'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# ALCH - Alchemy: Medicine, Food, Water, etc..
def writeRecToT3D_ALCH(f, record):
	if 'MODL' in GRUPS['ALCH'][record['NAME']]:
		model = GRUPS['ALCH'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['ALCH'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['ALCH'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Armor
def writeRecToT3D_ARMO(f, record):
	if 'MODL' in GRUPS['ARMO'][record['NAME']]:
		model = GRUPS['ARMO'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['ARMO'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['ARMO'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Books
def writeRecToT3D_BOOK(f, record):
	if 'MODL' in GRUPS['BOOK'][record['NAME']]:
		model = GRUPS['BOOK'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['BOOK'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['BOOK'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Keys
def writeRecToT3D_KEYM(f, record):
	if 'MODL' in GRUPS['KEYM'][record['NAME']]:
		model = GRUPS['KEYM'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['KEYM'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['KEYM'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Misc. Items
def writeRecToT3D_MISC(f, record):
	if 'MODL' in GRUPS['MISC'][record['NAME']]:
		model = GRUPS['MISC'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['MISC'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['MISC'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Weapons
def writeRecToT3D_WEAP(f, record):
	if 'MODL' in GRUPS['WEAP'][record['NAME']]:
		model = GRUPS['WEAP'][record['NAME']]['MODL']
		path, model = os.path.split(model)
		model = model.replace('.nif', '').replace('.NIF', '')

		scale = 1.0
		if 'XSCL' in record:
			scale = record['XSCL']

		f.write("""Begin Actor Class=StaticMeshActor Name=""" + str(record['NAME']) + GRUPS['WEAP'][record['NAME']]['EDID'] + """ Archetype=StaticMeshActor'/Script/Engine.Default__StaticMeshActor'
         Begin Object Class=StaticMeshComponent Name="StaticMeshComponent0" Archetype=StaticMeshComponent'/Script/Engine.Default__StaticMeshActor:StaticMeshComponent0'
         End Object
         Begin Object Name="StaticMeshComponent0"
            StaticMesh=StaticMesh'/Game/Meshes/""" + path + '/' + model + '.' + model + """'
            StaticMeshDerivedDataKey="STATICMESH_46A8778361B442A9523C54440EA1E9D_0db5412b27ab480f844cc7f0be5abaff_AF050A664CBE58381B1D05B5C07A33E600000000010000000100000000000000010000004000000000000000010000000000803F0000803F0000803F0000803F000000000000803F00000000000000000000344203030300000000"
            RelativeLocation=(X=""" + str(record['DATA'][0]) + """,Y=""" + str(record['DATA'][1]) + """,Z=""" + str(record['DATA'][2]) + """)
            RelativeRotation=(Pitch=""" + str(record['DATA'][3]) + """,Yaw=""" + str(record['DATA'][4]) + """,Roll=""" + str(record['DATA'][5]) + """)
         	RelativeScale3D=(X=""" + str(scale) + """, Y=""" + str(scale) + """, Z=""" + str(scale) + """)
         End Object
         StaticMeshComponent=StaticMeshComponent0
         RootComponent=StaticMeshComponent0
         ActorLabel=\"""" + str(record['NAME']) + GRUPS['WEAP'][record['NAME']]['EDID'] + """\"
      End Actor\n""")

# Dict to help organize T3D output functions
# by the type of object/record being written
writeRecToT3DFuncs = {
	'STAT' : writeRecToT3D_STAT,
	'DOOR' : writeRecToT3D_DOOR,
	'FURN' : writeRecToT3D_FURN,
	'CONT' : writeRecToT3D_CONT,
	'AMMO' : writeRecToT3D_AMMO,
	'ACTI' : writeRecToT3D_ACTI,
	'ALCH' : writeRecToT3D_ALCH,
	'ARMO' : writeRecToT3D_ARMO,
	'BOOK' : writeRecToT3D_BOOK,
	'KEYM' : writeRecToT3D_KEYM,
	'MISC' : writeRecToT3D_MISC,
	'WEAP' : writeRecToT3D_WEAP,
}

if len(sys.argv) > 2:
	for arg in sys.argv[2:]:
		if arg == '-dumpgroups':
			SETTINGS['dumpgroups'] = True
		elif arg == '-nomanifests':
			SETTINGS['nomanifests'] = True
		elif arg == '-allsubs':
			SETTINGS['allsubs'] = True

if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
	# Parse the .ESM and populate our GRUPS dict
	# with all of the information from relevant and
	# parsable top groups
	parseESM(str(sys.argv[1]))

	# Dump top group data to file
	if SETTINGS['dumpgroups']:
		writeObjectsToFile()

	# Generate cell manifests as .T3D files
	if not SETTINGS['nomanifests']:	
		generateCellManifests()
else:
	print('Please specify a path to a valid .ESM file.')
