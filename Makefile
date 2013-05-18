cacheDirs  := cache __pycache__
buildDir   = build
debugFlg   = 
PACKAGE = flscp
#Directory with ui and resource files
UI_FILES = cp.ui mailform.ui maileditor.ui
RESOURCES = logos.qrc
STATIC_LIBS = libs
PYTHONS = $(wildcard $(PACKAGE)/*.py)
RESOURCE_DIR = $(PACKAGE)/res
UI_DIR = $(PACKAGE)/ui

COMPILED_UI = $(UI_FILES:%.ui=$(buildDir)/$(PACKAGE)/ui_%.py)
COMPILED_RESOURCES = $(RESOURCES:%.qrc=$(buildDir)/$(PACKAGE)/%_rc.py)
COMPILED_PYTHONS = $(PYTHONS:%.py=$(buildDir)/%.py)

PYUIC = pyuic4-python3.2
PYRCC = pyrcc4
PYTHON = python3.2
PYPARM = 
RSYNC = rsync
RSYNCPARM = -rupE

all: createDir debug libs

run: all
	$(PYTHON) $(PYPARM) $(buildDir)/$(PACKAGE)/flscp.py

server: all
	$(PYTHON) $(PYPARM) $(buildDir)/$(PACKAGE)/flscpserver.py

release: PYPARM := -OO
release: pythons resources ui

debug: debugFlg := -x
debug: PYPARM := -v
debug: pythons resources ui

createDir:
	@if [ ! -d "$(buildDir)/$(PACKAGE)" ]; then mkdir -p $(buildDir)/$(PACKAGE); fi

pythons: $(COMPILED_PYTHONS)
$(buildDir)/%.py: %.py
	cp $< $@
	chmod +x $@

libs: $(buildDir)/$(PACKAGE)/$(STATIC_LIBS)
$(buildDir)/$(PACKAGE)/$(STATIC_LIBS):
	$(RSYNC) $(RSYNCPARM) $(PACKAGE)/$(STATIC_LIBS)/ $(buildDir)/$(PACKAGE)/$(STATIC_LIBS)/

#.PHONY: $(buildDir)/$(PACKAGE)/$(STATIC_LIBS)

resources: $(COMPILED_RESOURCES)  
ui: $(COMPILED_UI)

$(buildDir)/$(PACKAGE)/ui_%.py: $(UI_DIR)/%.ui
	$(PYUIC) $(debugFlg) $< -o $@
 
$(buildDir)/$(PACKAGE)/%_rc.py: $(RESOURCE_DIR)/%.qrc
	$(PYRCC) -py3 $< -o $@

clean:
	$(RM) -rvf $(COMPILED_UI)
	$(RM) -rvf $(COMPILED_RESOURCES)
	$(RM) -rvf $(COMPILED_PYTHONS)
	$(RM) -rvf ${cacheDirs}
