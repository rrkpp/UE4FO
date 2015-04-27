# UE4FO
Python script to parse GameBryo .ESM files into UE4 importable .T3D map files (or raw data via .txt).

# How to Use
Invoke ue4fo.py script from command line, passing a path to a valid GameBryo .ESM file to be parsed.
Example: python ue4fo.py FalloutNV.esm

Optional Arguments:
* -dumpgroups: Dumps data from .ESM top-groups to files in /topgroups directory. Useful if you want the raw data in a human readable format, especially if you're using this script for non-UE4 projects and just want .ESM data.
* -nomanifests: By default this script generates UE4 importable .T3D files from GameBryo cell data, populated with static meshes, weapons, etc.. Use this flag if you don't want to generate these files.
* -allsubs: Debug flag, prints to console and notifies of any records that aren't supported.

# Configuration
The only thing you should have to configure is the scale of the .T3D files generated for UE4. Default scale is 1.4 (This is what I felt was appropriate in my own personal testing). If you want to change the way your levels are scaled when imported into UE4, just edit the script and change the line that reads,

'scale' : 1.4

to your liking.

# License
This code is free to use and modify in any non-commercial projects. For licensing this work or any derivitaves of it for commercial use, please contact me via GitHub.
