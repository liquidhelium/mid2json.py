# author: Helium
# import pyjion
# pyjion.enable()
import mido
import typing
from typing import Any
import math
import json



def trySerialize(obj: Any) -> typing.Union[dict[Any], Any]:
    if isinstance(obj, Serializeable):
        return obj.serialize()
    elif isinstance(obj, dict):
        return {key: trySerialize(value) for key, value in obj.items()}
    elif isinstance(obj, typing.Iterable) and not isinstance(obj, str):
        return [trySerialize(item) for item in obj]
    else:
        return obj


class Serializeable:

    def __getattribute__(self, __name: str) -> Any:
        if not __name.startswith("S_") and hasattr(self, "S_" + __name):
            return object.__getattribute__(self, "S_" + __name)
        else:
            return object.__getattribute__(self, __name)

    def __setattr__(self, __name: str, __value: Any) -> None:
        object.__setattr__(self, "S_" + __name, __value)

    def serialize(self):
        return {
            key[2:]: trySerialize(value)
            for key, value in self.__dict__.items() if key.startswith("S_")
        }


class RpeTime(Serializeable):

    def __init__(self, beat: int, numerator: int, denominator: int) -> None:
        self.beat = beat
        self.numerator = numerator
        self.denominator = denominator

    def serialize(self):
        return [self.beat, self.numerator, self.denominator]


class RpeNote(Serializeable):

    def __init__(self,
                 startTime: RpeTime,
                 positionX: float,
                 endTime: RpeTime = None,
                 above=1,
                 alpha=255,
                 isFake=0,
                 size=1.0,
                 speed=1.0,
                 type=1,
                 visibleTime=999999.0,
                 yOffset=0.0) -> None:
        self.above = above
        self.alpha = alpha
        self.endTime = endTime or startTime
        self.isFake = isFake
        self.positionX = positionX
        self.size = size
        self.speed = speed
        self.startTime = startTime
        self.type = type
        self.visibleTime = visibleTime
        self.yOffset = yOffset


defaultEventLayers = [{
    "alphaEvents": [{
        "easingType": 1,
        "end": 200,
        "endTime": [1, 0, 1],
        "linkgroup": 0,
        "start": 0,
        "startTime": [0, 1, 4]
    }],
    "moveXEvents": [{
        "easingType": 1,
        "end": 0.0,
        "endTime": [0, 1, 8],
        "linkgroup": 0,
        "start": 0.0,
        "startTime": [0, 0, 1]
    }, {
        "easingType": 1,
        "end": 0.0,
        "endTime": [1, 0, 1],
        "linkgroup": 0,
        "start": 0.0,
        "startTime": [0, 1, 8]
    }],
    "moveYEvents": [{
        "easingType": 1,
        "end": -450.0,
        "endTime": [0, 1, 8],
        "linkgroup": 0,
        "start": -450.0,
        "startTime": [0, 0, 1]
    }, {
        "easingType": 18,
        "end": -250.0,
        "endTime": [1, 0, 1],
        "linkgroup": 0,
        "start": -450.0,
        "startTime": [0, 1, 8]
    }],
    "rotateEvents": [{
        "easingType": 1,
        "end": 0.0,
        "endTime": [1, 0, 1],
        "linkgroup": 0,
        "start": 0.0,
        "startTime": [0, 0, 1]
    }],
    "speedEvents": [{
        "end": 8.0,
        "endTime": [1, 0, 1],
        "linkgroup": 0,
        "start": 8.0,
        "startTime": [0, 0, 1]
    }]
}]


class RpeJudgeLine(Serializeable):

    def __init__(self,
                 Group=0,
                 Name="main",
                 Texture="line.png",
                 eventLayers=defaultEventLayers,
                 isCover=1,
                 notes=[]) -> None:
        self.Group = Group
        self.Name = Name
        self.Texture = Texture
        self.eventLayers = eventLayers
        self.isCover = isCover
        self.notes = notes
        self.numOfNotes = len(notes)

    def pushNewNote(self, note: RpeNote):
        self.notes.append(note)
        self.numOfNotes += 1

    def recountNotes(self):
        self.numOfNotes = len(self.notes)


class BPMEvent(Serializeable):

    def __init__(self, bpm: int, startTime=RpeTime(0, 0, 1)):
        self.bpm = bpm
        self.startTime = startTime


class RpeMetaInfo(Serializeable):

    def __init__(self,
                 id: str,
                 RPEVersion=100,
                 charter="mid2json",
                 composer="nameless",
                 level=0,
                 name="Generated",
                 offset=0,
                 song=None,
                 background=None) -> None:
        self.id = id
        self.RPEVersion = RPEVersion
        self.charter = charter
        self.composer = composer
        self.level = level
        self.name = name
        self.offset = offset
        self.song = song or id + ".jpg"
        self.background = background or id + ".mp3"


defaultLineGroup = ["Default", "", "", "", "", "", "", "", "", ""]


class RpeChart(Serializeable):

    def __init__(self,
                 BPMList,
                 META,
                 judgeLineGroup=defaultLineGroup,
                 judgeLineList=[]):
        self.BPMList = BPMList
        self.META = META
        self.judgeLineGroup = judgeLineGroup
        self.judgeLineList = judgeLineList

    def pushNewLine(self, line: RpeJudgeLine):
        self.judgeLineList.append(line)


def midiTickToRpeTime(tick: int, ticks_per_beat: int) -> RpeTime:
    return RpeTime(math.floor(tick / ticks_per_beat), tick % ticks_per_beat,
                   ticks_per_beat)


def midiTrackToMeta(track: mido.MidiTrack[mido.MetaMessage],
                    id=114514) -> RpeMetaInfo:
    return RpeMetaInfo(str(id), name=track.name or "Generated")


def midiPitchToXValue(pitch: int) -> float:
    # rpe屏幕宽625*2; midi 共127键, 标准88键的最低处是#21
    # 我们希望 C4(中央C)在屏幕中间, 即#60
    return (pitch - 16) / 88 * 625 * 2 - 625


def midiTrackToBpm(track: mido.MidiTrack, ticks_per_beat) -> list[BPMEvent]:

    def _messageToBpmEv(msg: mido.MetaMessage) -> BPMEvent:
        return BPMEvent(mido.tempo2bpm(msg.tempo),
                        midiTickToRpeTime(msg.time, ticks_per_beat))

    return [_messageToBpmEv(msg) for msg in track if msg.type == "set_tempo"]


def midiTrackToNotes(track: mido.MidiTrack, ticks_per_beat) -> list[RpeNote]:
    currentTick = 0

    def _messageToNote(msg: mido.Message):
        # 有效的类型: note_on, note_off
        nonlocal currentTick
        currentTick += msg.time
        if msg.type == "note_on":
            return RpeNote(midiTickToRpeTime(currentTick, ticks_per_beat),
                           midiPitchToXValue(msg.note))

    return [
        i for i in [
            _messageToNote(msg) for msg in track
            if (msg.type == "note_on" or msg.type == "note_off")
        ] if i
    ]


def midiTrackToJudgeLine(track: mido.MidiTrack,
                         ticks_per_beat) -> RpeJudgeLine:
    return RpeJudgeLine(Name=track.name,
                        notes=midiTrackToNotes(track, ticks_per_beat))


def isMeta(track: mido.MidiTrack):
    for i in track:
        if not i.is_meta:
            return False
    return True


def allMetas(file: mido.MidiFile) -> mido.MidiTrack:
    return mido.merge_tracks([i for i in file.tracks if isMeta(i)])


def mid2json(file: mido.MidiFile, id=114514) -> str:
    judgelineList = [
        midiTrackToJudgeLine(i, file.ticks_per_beat) for i in file.tracks
        if not isMeta(i)
    ]
    allMeta = allMetas(file)
    return json.dumps(
        trySerialize(
            RpeChart(BPMList=midiTrackToBpm(allMeta, file.ticks_per_beat),
                     META=midiTrackToMeta(allMeta, id),
                     judgeLineList=judgelineList)))

import  sys
import time
filePath = sys.argv[1] if len(sys.argv) - 1 else input("输入谱面路径:")
print("读取中... 现在是", time.strftime("%H:%M:%S"))
midi = mido.MidiFile(filePath)
id = input("输入谱面id:")
print("生成中...")
print(mid2json(midi, int(id)), file=open(id+".json","w"))