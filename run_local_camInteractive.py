#!/usr/bin/env python
# -*- coding: utf-8 -*-

#
# Optical Braille Recognition - speech guided interactive user interface for Angelina Reader
#
# This script either processes either
#   a) single frames from a live webcam video or 
#   b) existing images (in folder args.input_dir) 
#
# Place braille sheets (or book) on a dark background.
# Set up light and camera as described here: https://angelina-reader.ru/help/#how_to_photo
# When processing images, the script seperates bright area from background, 
# then decides if orientation is portrait (1 page) or landscape (2 pages, book),
# in case of landscape orientation extracts 2 single pages,
# then performs optical braille recognition using Angelina Reader
# and optionally speaks out results using pyttsx3 / picoTTS
#
# thanks to:
#   https://www.codegrepper.com/code-examples/python/python+capture+image+from+webcam
#   https://stackoverflow.com/questions/13887863/extract-bounding-box-and-save-it-as-an-image
#   https://github.com/IlyaOvodov/AngelinaReader
#


import cv2
import os
import glob
import argparse
from pathlib import Path
from pygame import mixer

import local_config
import model.infer_retinanet as infer_retinanet

# file paths and filename prefixes
model_weights = 'model.t7'
results_dir = './results'
results_prefix = 'Seite'

MIN_AREA=100000   # for detecting a valid page
WINDOW_WIDTH=500  # for displaying result windows

# keycodes for windows and linux
UP_ARROW_KEY_WINDOWS = 2490368
DOWN_ARROW_KEY_WINDOWS = 2621440   
LEFT_ARROW_KEY_WINDOWS = 2424832
RIGHT_ARROW_KEY_WINDOWS = 2555904
PAGEUP_KEY_WINDOWS = 2162688
PAGEDOWN_KEY_WINDOWS = 2228224

UP_ARROW_KEY_LINUX = 65362
DOWN_ARROW_KEY_LINUX = 65364
LEFT_ARROW_KEY_LINUX = 65361
RIGHT_ARROW_KEY_LINUX = 65363
PAGEUP_KEY_LINUX = 65366
PAGEDOWN_KEY_LINUX = 65365

voiceSpeed=150

langMapping = {
	"DE": ["de-DE","German"],
	"EN": ["en-US","English"]
}

lastKey=-1
img_counter = 1
fromCam=False
readLinenumbers=True
frame=None
cam=None
fn=0


def announce (text):
    global fn
    global lastKey

    if (len(text)==0):
        announce ("leere Zeile")
        return
        
    print(text, flush=True)
    if (args.silent == True):
        return
    
    if onWindows == True:
        # speechSynthesizer.say(text)
        fn = (fn+1) % 2  # a workaround because ttsx3 does not close the most recent file correctly
        tempFile="temp{}.wav".format(fn)
        speechSynthesizer.setProperty('rate', voiceSpeed)
        speechSynthesizer.save_to_file(text, tempFile)
        speechSynthesizer.runAndWait()
        speechSynthesizer.stop()
    else:
        # use google TTS
        #tts = gTTS(text, lang='de')
        #tts.save("temp.mp3")
        
        # use PicoTTS
        os.system('pico2wave --lang={} -w pico.wav "{}"'.format(langMapping.get(args.lang)[0],text))
        os.system("sox " + "pico.wav temp.wav tempo {}".format(voiceSpeed/100))
        tempFile="temp.wav"

    # using pygame mixer to interrupt/pause voice playback!
    
    try:
        if (os.path.getsize(tempFile) > 500):  # sanity check to prevent empty soundfile
            mixer.music.load(tempFile)        
            mixer.music.play()
    except:
        print ("Could not play music file (maybe empty)!")
    
    pause=False
    lastKey=-1
    while (mixer.music.get_busy() and lastKey==-1) or (pause == True):
        lastKey = cv2.waitKeyEx(10)
        if lastKey == 27:         # ESC: end readout
                mixer.music.stop()
        if lastKey == ord('p'):   # p: pause/resume ongoing speech output
            if pause==False:
                mixer.music.pause()                
            else:
                mixer.music.unpause()
                lastKey=-1
            pause = not pause

def expandUnreadableCharacters(line,expandSpaceKey):
    if (expandSpaceKey==True):
        line=line.replace(" ", "(Leertaste) ")
    line=line.replace("~?~", " (unbekannt) ")
    line=line.replace("\"", " (Hochkomma) ")
    line=line.replace(":", " (Doppelpunkt) ")
    line=line.replace(";", " (Strichpunkt) ")
    line=line.replace(",", " (Beistrich) ")
    line=line.replace(".", " (Punkt) ")
    line=line.replace("-", " (Minus) ")
    line=line.replace("+", " (Plus) ")
    line=line.replace("*", " (Stern) ")
    return(line)

def readResult():
    global img_counter
    global readLinenumbers
    global lastKey

    announce("Vorlesen der Ergebnisse für Seite {}".format(img_counter))

    marked_name = "{}{}{:04d}.marked.txt".format(results_dir,results_prefix,img_counter)
    marked_jpg = "{}{}{:04d}.marked.jpg".format(results_dir,results_prefix,img_counter)    

    if (not os.path.exists(marked_name)) or (not os.path.exists(marked_jpg)):
        announce ("Ergebnisdateien für diese Seite nicht vorhanden, bitte zuerst Bild verarbeiten")
        return


    file1 = open(marked_name, 'r', encoding='utf-8', errors='ignore')
    Lines = file1.readlines()
    if (len (Lines) < 1):
        announce ("es konnten keine Ergebnisse für diese Seite gefunden werden")
        return

    windowName="OBR-Ergebnis Seite {}".format(img_counter)
    cv2.namedWindow(windowName)
    cv2.moveWindow(windowName, 50+WINDOW_WIDTH,40)
    img = cv2.imread(marked_jpg)
    cv2.imshow(windowName, resizeImg(img))
      
    actLine = 0
    actLetter = -1
    readNextLetter = False
    readNextLine = True
    while True:
        if readNextLine == True:
            line=Lines[actLine].strip()
            line=expandUnreadableCharacters(line, False)
            if (readLinenumbers==True):
                announce("Zeile{}: {}".format(actLine+1, line.strip()))
            else:
                announce(line.strip())
        elif readNextLetter == True:
            line=Lines[actLine].strip()
            letter=line[actLetter]
            announce(expandUnreadableCharacters(letter,True))
            readNextLetter=False
        else:
            if readNextLine == False:
                lastKey = cv2.waitKeyEx(10)
            
        if (lastKey == UP_ARROW_KEY and actLine > 0):   # up arrow
            actLine-=1
            actLetter=-1
            readNextLetter=False
            readNextLine=True
        elif (lastKey == DOWN_ARROW_KEY and actLine < len(Lines)):   # down arrow
            actLine+=1
            actLetter=-1
            readNextLetter=False
            readNextLine=True
        elif (lastKey == LEFT_ARROW_KEY):
            readNextLine=False
            if (actLetter>0):
                readNextLetter=True
                actLetter-=1
            else:
                announce("Zeilenanfang")
                actLetter=-1
        elif (lastKey == RIGHT_ARROW_KEY):
            readNextLine=False
            if (actLetter<len(line)-1):
                readNextLetter=True
                actLetter+=1
            else:
                announce("Zeilenende")
                actLetter=len(line)
        elif (lastKey == -1) and (readNextLine == True):   # no key -> progress to next line!
            actLine+=1
        elif (lastKey == 27):   # ESC: end readout
            actLine = len(Lines)
            announce ("Vorlesemodus beendet")
        elif lastKey == ord('z'):   # z pressed
            readLinenumbers = not readLinenumbers
            if (readLinenumbers==True):
                announce("Zeilennummern werden vorgelesen")
            else:
                announce("Zeilennummern werden nicht vorgelesen")
            
        if actLine == len (Lines):
            break
            
    cv2.destroyWindow(windowName)
    
def process_image (img,x,y,w,h):
    global img_counter

    ROI = img[y:y+h, x:x+w]
    frameCopy = img.copy()
    cv2.rectangle(frameCopy,(x,y),(x+w,y+h),(10,10,255),2)
    cv2.imshow("brailleImage", resizeImg(frameCopy))
    cv2.waitKey(1)

    img_name = "{}{}{:04d}".format(results_dir,results_prefix,img_counter)
    if (os.path.exists(img_name+".marked.brl")==True):
        os.remove(img_name+".marked.brl")
    if (os.path.exists(img_name+".marked.txt")==True):
        os.remove(img_name+".marked.txt")
    if (os.path.exists(img_name+".marked.jpg")==True):
        os.remove(img_name+".marked.jpg")
        
    img_name=img_name+".png"
    
    cv2.imwrite(img_name, ROI)
    recognizer.run_and_save(img_name, results_dir, target_stem=None,
                                           lang=args.lang, extra_info=None,
                                           draw_refined=recognizer.DRAW_NONE,
                                           remove_labeled_from_filename=False,
                                           find_orientation=args.orient,
                                           align_results=True,
                                           process_2_sides=False,
                                           repeat_on_aligned=False,
                                           save_development_info=False)


def slice_and_process_image(frame):
    global img_counter
    if frame is None:
        announce ("Bildaten für Seite {} nicht vorhanden, Verarbeitung nicht möglich".format(img_counter))
        return
        
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    thresh = cv2.threshold(gray,0,255,cv2.THRESH_OTSU + cv2.THRESH_BINARY)[1]
    #cv2.imshow('thresh', thresh)

    # find contours of biggest bounding rectangle
    cnts = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    maxArea=0
    actIndex=0
    for c in cnts:
        x,y,w,h = cv2.boundingRect(c)
        if maxArea < w*h:
            maxArea= w*h
            maxContour=c
        actIndex+=1

    if (maxArea>MIN_AREA):
        x,y,w,h = cv2.boundingRect(maxContour)
        print("w: {}, h: {}, area: {}, ratio: {}".format(w,h,w*h,w/h), flush=True)
        if (w/h < 1.3 ):  # assume page with portrait orientation, extract 1 page
            process_image(frame,x,y,w,h)
                            
        else:   # assume book with landscape orientation, extract 2 pages!
            announce("Doppelseite erkannt, verarbeite linke Seite")
            half_w=round(w/2)
            process_image(frame,x,y,half_w,h)
            img_counter += 1
            announce("verarbeite rechte Seite")
            process_image(frame,x+half_w,y,half_w,h)
    else:
        announce("keine Seite erkannt"); 

def processFolder (importPath):
    global img_counter
    removeResults()
    img_files = list(Path(importPath).glob("*"))
    
    for img_file in img_files:
        ext = os.path.splitext(img_file)[-1].lower()
        if (ext==".jpg" or ext==".png") and (not ".marked" in os.path.basename(img_file)):
            announce('Verarbeite Seite {} aus Datei {}'.format(img_counter,os.path.basename(img_file)))
            frame = cv2.imread(str(img_file))
            slice_and_process_image(frame)
            img_counter += 1
    if (img_counter > 1):
        img_counter-=1


def removeResults():
    global img_counter
    announce("Lösche alle bestehenden Ergebnisdateien.")
    img_counter=1
    files = glob.glob('{}*'.format(results_dir))
    for f in files:
        os.remove(f)     
        
def getYesNo():
    while (True):
        k=cv2.waitKey(10)
        if k==ord('j'):
            return True
        if k==ord('n'):
            return False
        if k==-1 or k==0 or k==255:
            continue
        else:
            announce("bitte j für ja oder n für nein drücken")

def resizeImg(image):
    (h, w) = image.shape[:2]
    r = WINDOW_WIDTH / float(w)
    dim = (WINDOW_WIDTH, int(h * r))
    return cv2.resize(image, dim, cv2.INTER_AREA)

def openCamera():
    global cam
    global fromCam
    # checks the first 10 cams!
    i = 0
    while i < 10:
        print("checking Camera {}".format(i))
        cam = cv2.VideoCapture(i)
        ret, frame = cam.read()
        if ret:        
        # if cam.read()[0]:
            cv2.imshow("brailleImage", resizeImg(frame))
            announce ("Kamera Index {} gefunden, Name:{}".format(i,cam.getBackendName()))
            announce ("diese Kamera verwenden?");
            if getYesNo()==True:
                announce ("ja")
                fromCam=True
                break
            else:
                announce ("nein")
                cam.release()
        i+=1       

def printHelp():
    announce("Taste h: Ausgabe Hilfetext")
    announce("Taste k: zwischen Kamera und Bilddateien wechseln")
    announce("Leertaste: Bildverarbeitung der aktuellen Seite starten")
    announce("Taste l: löschen der bestehenden Bild- und Ergebnisdateien")
    announce("Taste v: Vorlesemodus")
    announce("Bildtaste rauf: nächste Seite")
    announce("Bildtaste runter: vorige Seite")
    announce("Pfeiltaste rauf: vorige Zeile lesen")
    announce("Pfeiltaste runter: nächste Zeile lesen")
    announce("Pfeiltaste rechts: nächster Buchstabe")
    announce("Pfeiltaste links: voriger Buchstabe")
    announce("Taste z: Zeilennummern vorlesen oder nicht")
    announce("Taste p: Pausieren der laufenden Sprachausgabe")
    announce("Plustaste: schneller sprechen")
    announce("Minustaste: langsamer sprechen")
    announce("Escape: Programm beenden")


# program execution starts here!

parser = argparse.ArgumentParser(description='Angelina Braille Reader: optical Braille text recognizer - interactive version using camera input.')
parser.add_argument('input', nargs='?', type=str, help='(optional): Input source to be processed: directory name or "camera". If not specified, existing files in results folder will be used')
#parser.add_argument('results_dir', type=str, help='Output directory for results.')
parser.add_argument('-l', '--lang', type=str, default='DE', help='Document language (RU, EN, DE, GR, LV, PL, UZ or UZL). If not specified, default is DE')
parser.add_argument('-o', '--orient', action='store_false', help="Don't find orientation, use original file orientation (faster)")
parser.add_argument('-s', '--silent', action='store_true', help="silent mode, do not generate speech output")
#parser.add_argument('-2', dest='two', action='store_true', help="Process 2 sides")
args = parser.parse_args()

results_dir=os.path.join(results_dir, '')  # add trailing slash if necessary
if not Path(results_dir).exists():
    print('results directory does not exist: ' + results_dir)
    exit()
    

def selectVoice(engine, language):
    for voice in engine.getProperty('voices'):
        print (voice)
        #print(voice.languages)
        #if language in voice.languages:   # didnt work under windows..
        if voice.name.find(langMapping.get(language)[1]) > 0:
            engine.setProperty('voice', voice.id)
            return True

    raise RuntimeError("Language '{}' not found".format(language))

# Initialize the speech synthesizer and other OS-dependent resources
if os.name=='nt':
    onWindows=True
    import pyttsx3
    speechSynthesizer = pyttsx3.init()
    selectVoice(speechSynthesizer, args.lang) 
    # speechSynthesizer.setProperty('voice', voices)
    speechSynthesizer.setProperty('rate', 200)
    speechSynthesizer.setProperty('volume', 0.7)
    UP_ARROW_KEY = UP_ARROW_KEY_WINDOWS
    DOWN_ARROW_KEY = DOWN_ARROW_KEY_WINDOWS 
    LEFT_ARROW_KEY = LEFT_ARROW_KEY_WINDOWS
    RIGHT_ARROW_KEY = RIGHT_ARROW_KEY_WINDOWS
    PAGEUP_KEY = PAGEUP_KEY_WINDOWS
    PAGEDOWN_KEY = PAGEDOWN_KEY_WINDOWS
else:
    onWindows=False
    #from gtts import gTTS
    UP_ARROW_KEY = UP_ARROW_KEY_LINUX
    DOWN_ARROW_KEY = DOWN_ARROW_KEY_LINUX
    LEFT_ARROW_KEY = LEFT_ARROW_KEY_LINUX
    RIGHT_ARROW_KEY = RIGHT_ARROW_KEY_LINUX
    PAGEUP_KEY = PAGEUP_KEY_LINUX
    PAGEDOWN_KEY = PAGEDOWN_KEY_LINUX


mixer.init()

# welcome message, create live window
announce("Programm startet ...")

# Initialize the webcam and opencv
cv2.namedWindow("brailleImage")
cv2.moveWindow("brailleImage", 10,50)

# Initialize the Braille recognizer
recognizer = infer_retinanet.BrailleInference(
    params_fn=os.path.join(local_config.data_path, 'weights', 'param.txt'),
    model_weights_fn=os.path.join(local_config.data_path, 'weights', model_weights),
    create_script=None)

if args.input:
    if (args.input=='camera'):
        openCamera()
    else:
        announce("Verarbeite Dateien aus Verzeichnis "+args.input)
        processFolder(args.input)
        announce("Verarbeitung abgeschlossen")
        img_counter=1

announce ("Bereit. Taste h für Hilfe drücken.");
updateImage = True

# main loop
while True:
    actfile="{}{}{:04d}.png".format(results_dir,results_prefix,img_counter)

    if updateImage == True:
        if (fromCam==True):
            if cam==None:
                openCamera()
            ret, frame = cam.read()
            if not ret:
                announce("Kamera konnte Seite {} nicht aufnehmen.".format(img_counter))
                # fromCam=False
                updateImage=False
        elif (os.path.exists(actfile)==True):
            frame = cv2.imread(actfile)
            updateImage=False
        else:
            announce("Datei für Seite {} nicht vorhanden".format(img_counter))
            updateImage=False
            continue

    if frame is not None:
        cv2.imshow("brailleImage", resizeImg(frame))

    k = cv2.waitKeyEx(10)
    if k%256 == 27:       # ESC pressed
        announce("Escape gedrückt, Programm wird beendet")
        break

    elif k%256 == ord('l'):    # l pressed
        removeResults()

    elif k%256 == ord('k'):    # k pressed
        fromCam = not fromCam
        if fromCam==True:
            announce("Kamera eingeschaltet - verwende Kamerabild")
        else:
            announce("Kamera ausgeschaltet - verwende bestehende Ergebnisdateien")
        updateImage=True

    elif k%256 == ord('v'):    # v pressed
        readResult()            

    elif k%256 == ord('h'):    # h pressed
        printHelp()
        
    elif k%256 == ord('-'):    # - pressed
        voiceSpeed -= 10
        announce("Sprechgeschwindigkeit {} Prozent".format(voiceSpeed))

    elif k%256 == ord('+'):    # + pressed
        voiceSpeed += 10
        announce("Sprechgeschwindigkeit {} Prozent".format(voiceSpeed))
            
    elif k == PAGEDOWN_KEY:        # previous page
        updateImage=True
        if (img_counter>1):
            img_counter-=1
        announce("Seite {}".format(img_counter))

    elif k == PAGEUP_KEY:          # next page
        updateImage=True
        img_counter+=1
        announce("Seite {}".format(img_counter))

    elif k == UP_ARROW_KEY or k == DOWN_ARROW_KEY or k == RIGHT_ARROW_KEY or k == LEFT_ARROW_KEY:     # up or down arrow pressed
        announce("Zum Vorlesen der aktuellen Seite Taste v drücken")

    elif k%256 == ord(' '):     # SPACE pressed
        updateImage=True
        if fromCam==True:
            announce("verarbeite Seite {} von Kamera".format(img_counter))
        else:
            announce("verarbeite Seite {} aus bestehender Datei".format(img_counter))
        slice_and_process_image(frame)
        announce("Verarbeitung abgeschlossen")

    elif k==-1:  # normally -1 returned,so don't print it
        continue
    else:
        print ("Tastencode {} nicht verwendet".format(k)) # else print key value
        
if (cam != None):
    cam.release()
cv2.destroyAllWindows()
