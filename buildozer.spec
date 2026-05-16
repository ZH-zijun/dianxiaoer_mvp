[app]

# (str) Title of your application
title = 店小二 - AI 记账助手
version = 0.0.1
android.accept_sdk_license = True

# 锁定 Python 版本，避免构建时自动检测导致错误
requirements = python3==3.11.1,kivy==2.3.0,sounddevice,pycryptodome,websocket-client

# 手动指定 hostpython 为 3.11
android.hostpython = python3.11

# (str) Package name
package.name = dianxiaoer

# (str) Package domain (needed for android/ios packaging)
package.domain = com.dianxiaoer

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,ttf,json

# (list) List of inclusions using pattern matching
#source.include_patterns = assets/*,images/*.png

# (list) Source files to exclude
#source.exclude_exts = spec

# (list) List of directory to exclude (let empty to not exclude anything)
#source.exclude_dirs = tests, bin, venv

# (list) List of exclusions using pattern matching
# Do not prefix with './'
source.exclude_patterns = build,.workbuddy,*.md,*.pyc,__pycache__,*.jet,.venv,.git

# (list) List of directory to add (let empty to not include anything)
source.include_dirs = libs,assets

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy

# (str) Supported orientation (landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) List of service to declare
#services = NAME:ENTRYPOINT_TO_PY,NAME2:ENTRYPOINT2_TO_PY

# Android specific
# ---------------

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1

# (string) Android logcat filters to use
#logcat_filters = *:S python:D

# (list) Permissions
android.permissions = INTERNET,RECORD_AUDIO,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK will support.
android.minapi = 21

# (int) Android SDK version to use
#android.sdk = 33

# (str) Android NDK version to use
#android.ndk = 25b

# (bool) Use --private data storage (True) or just --dir (False)
#android.private_storage = True

# (str) Android entry point, default is ok for Kivy-based app
#android.entrypoint = org.kivy.android.PythonActivity

# (list) List of Java .jar files to add to the libs so that javac can find them
#android.add_jars = foo.jar,bar.jar

# (list) List of Java files to add to the project. Please read the docs for
# more information about using Java in p4a
#android.add_src = your/java/files/directory

# (str) python-for-android branch to use
#p4a.branch = master

# (str) OSGi framework to use (currently only org.renpy.android is supported)
#android.osgi = False

# (bool) Copy instead of linking libraries (useful for debugging / building)
#android.copy_libs = 1

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.arch = arm64-v8a

# iOS specific
# -------------

# (list) List of requirements (str) needed at runtime
ios.requirements =

# (str) Name of the application displayed on iOS
ios.display_name = 店小二

# (bool) Force to use storyboard in iOS
ios.storyboard =

# (str) URL scheme to call the app (URL with custom scheme)
ios.url_scheme =

# (str) URL scheme to call the app from browser (URL with custom scheme)
ios.browser_open_url =

# (str) Application icon file path (None for app icon default)
#icon.filename = %(source.dir)s/data/images/%(package.name)s-icon.png

# (str) Application presplash file path
#presplash.filename = %(source.dir)s/data/images/%(package.name)s-presplash.png

# (str) Application icon background color (only used if no icon file)
icon.bg_color = 0x1a1a2e

# (list) Supported architectures
#android.arch = arm64-v8a,armeabi-v7a
