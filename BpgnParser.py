#!/usr/bin/python

# parse BPGN (game metadata + moves) into position strings

import os
import re
import sys

import Common
import BugLogic

class Move:
    def __init__(self):
        self.player = ''
        self.moveNum = ''
        self.san = ''
        self.comments = []
        pass

    def __str__(self):
        answer = self.moveNum + self.player + '. ' + self.san

        for c in self.comments:
            answer += ' {%s}' % c

        return answer

class MatchMovesOOOException(Exception):
    pass
class MatchZeroMovesException(Exception):
    pass

class Match:
    def __init__(self):
        self.initState = Common.initBugFEN
        self.moves = []
        self.tags = {}
        self.comments = []
        self.states = [self.initState]

        self.movesSeenBefore = {}

    def populateState(self, i):
        while len(self.moves) >= len(self.states):
            self.states += ['']
        
        fullMove = self.moves[i].moveNum + self.moves[i].player + '. ' + self.moves[i].san
        #print "populating on move: -%s-" % fullMove

        # when someone forfeits on time, a repeat instance of their last move (even the time) is
        # logged ... we thus remember moves we've seen before and not act on them
        if fullMove in self.movesSeenBefore:
            self.states[i+1] = self.states[i]
        else:
            self.movesSeenBefore[fullMove] = 1
            self.states[i+1] = BugLogic.nextState(self.states[i], self.moves[i].player, self.moves[i].san)

        #print "returned: -%s-" % self.states[i+1]
        #print '----------'

    def populateStates(self):
        self.states = [self.initState]

        for i in range(len(self.moves)):
            self.populateState(i)

    def incrMoveNum(self, fullMove):
        m = re.match(r'^(\d+)([AaBb])$', fullMove)
        [num, letter] = [int(m.group(1)), m.group(2)]
        
        if letter in 'ab':
            num += 1

        letter = {'A':'a', 'a':'A', 'B':'b', 'b':'B'}[letter]

        return str(num) + letter

    def sanityCheck(self):
        # does the game have ANY moves in it?
        if len(self.moves) == 0:
            raise MatchZeroMovesException("no moves recorded")

        # does the game have missing/out-of-order moves in it?
        expectA = '1A'
        expectB = '1B'
        for m in self.moves:
            fullMove = m.moveNum + m.player

            if fullMove == expectA:
                expectA = self.incrMoveNum(expectA)
            elif fullMove == expectB:
                expectB = self.incrMoveNum(expectB)
            else:
                raise MatchMovesOOOException("expected move %s or %s (got instead %s)" % \
                    (expectA, expectB, m.moveNum))

    def __str__(self):
        answer = '%s[%s],%s[%s] vs %s[%s],%s[%s]\n' % ( \
            self.tags['WhiteA'], self.tags['WhiteAElo'], self.tags['BlackA'], self.tags['BlackAElo'], \
            self.tags['BlackB'], self.tags['BlackBElo'], self.tags['WhiteA'], self.tags['WhiteAElo'] \
        )

        answer += "TAGS:\n"
        for tag,value in self.tags.iteritems():
            answer += "%s: \"%s\"\n" % (tag, value)
        answer += "COMMENTS:\n"
        for c in self.comments:
            answer += c + "\n"
        answer += "MOVES (%d total):\n" % len(self.moves)
        for m in self.moves:
            answer += str(m) + "\n"
        return answer

class MatchIteratorFile:
    def __init__(self, path):
        self.path = path

        self.fp = open(path, 'r')
        self.lineNum = -1

    def __iter__(self):
        self.fp.seek(0, 0)
        self.lineNum = -1
        return self

    def peekLine(self, doStrip=1):
        line = self.fp.readline()
        self.fp.seek(-1*len(line), 1)

        if doStrip:
            line = line.rstrip()

        return line

    def readLine(self):
        self.lineNum += 1
        temp = self.fp.readline().rstrip()
        #print "read: %s" % temp
        return temp

    def consumeNewLines(self):
        while 1:
            line = self.peekLine(False)
            if not line:
                return False
            if not re.match(r'^\s+$', line):
                break
            self.readLine()
        return True

    def next(self):
        # skip to next match
        #print "consuming newlines at %s:%d" % (self.path, self.lineNum)
        if not self.consumeNewLines():
            raise StopIteration
        
        match = Match()
        match.initState = Common.initBugFEN

        #print "consuming tags at %s:%d" % (self.path, self.lineNum)
        line = self.readLine()
        if not re.match(r'^\[Event', line):
            raise Exception("expected Event tag at %s:%d" % (self.path, self.lineNum))

        while re.match(r'^\[', line):
            for m in re.finditer(r'\[(.*?) "(.*?)"\]', line):
                match.tags[m.group(1)] = m.group(2)

            line = self.readLine()

        #print "consuming optional comments and newlines at %s:%d" % (self.path, self.lineNum)
        while 1:
            if not self.consumeNewLines():
                raise StopIteration
            line = self.peekLine()
            m = re.match('^{(.*)}$', line)
            if m:
                match.comments.append(m.group(1))
                self.readLine()
            else:
                break

        #print "consuming movetext at %s:%d" % (self.path, self.lineNum)
        # join the rest of the lines (until newline separator) as the movetext
        moveText = self.readLine()
        while not re.match(r'^\s*$', self.peekLine()):
            moveText = moveText.rstrip() + self.readLine()

        if not re.match(r'^.*(0-0$|0-1$|1-0$|1/2-1/2$|\*$)', moveText):
            raise Exception("expected match movetext at %s:%d" % (self.path, self.lineNum))

        move = None

        while moveText and not re.match(r'^\s+$', moveText):
            # COMMENT TOKEN ... place onto match or onto a move
            m = re.match(r'^{(.*?)}\s*', moveText)
            if m:
                where = move or match
                where.comments.append(m.group(1))

            else:
                # MOVE NUMBER TOKEN ... save last move, start new one
                m = re.match(r'^(\d+)([abAB])\.\s*', moveText)
                if m:
                    if move:
                        match.moves.append(move)
                    move = Move()
                    move.moveNum = m.group(1)
                    move.player = m.group(2)

                else:
                    # SAN TOKEN ... encodes the move
                    regex = r'^(?:' + \
                        r'O-O-O|' + \
                        r'O-O|' + \
                        r'(?P<srcPiece>[PNBRQK])?' + \
                        r'(?P<srcHint>[a-h1-8]{1,2})?' + \
                        r'(?P<action>[x@])?' + \
                        r'(?P<dstSquare>[a-h][1-8])' + \
                        r'(?P<promote>=[PNBRQKpnbrqk])?' + \
                        r')' + \
                        r'(?P<check>[\+#])?' + \
                        r'\s*'
 
                    m = re.match(regex, moveText)
                    if m:
                        move.san = m.group(0)
                        move.san = move.san.rstrip()
                    
                    # END OF MATCH TOKEN ... done hopefully
                    else:
                        m = re.match(r'^(0-0$|0-1$|1-0$|1/2-1/2$|\*)$', moveText)
                        if m:
                            if match.tags['Result'] != m.group(1):
                                raise Exception("Result tag doesn't match " + \
                                    "movetext result at %s:%d" % \
                                    (self.path, self.lineNum))

                        # WTF?
                        else:
                            raise Exception("don't know how to proceed " + \
                                "with remaining movetext -%s- at %s:%d" % \
                                (moveText, self.path, self.lineNum))
                   
            # reduce the moveText by the size of the consumed token
            moveText = moveText[len(m.group(0)):]

        if move:
            match.moves.append(move)

       # print "consuming optional comments at %s:%d" % (self.path, self.lineNum)
        while 1:
            line = self.peekLine()
            m = re.match('^{(.*)}$', line)
            if m:
                match.comments.push(m.group(1))
            else:
                break

        # done
        return match

    def __del__(self):
        self.fp.close()

class MatchIteratorDir:
    def __init__(self, path):
        self.walkObj = os.walk(path)
        self.matchIterFileObj = None
        self.filesList = []

    def __iter__(self):
        return self

    def next(self):
        while 1:
            # first level: does the file iterator still have something left?
            if self.matchIterFileObj:
                try:
                    return self.matchIterFileObj.next()
                except StopIteration: 
                    self.matchIterFileObj = None
    
            # second level, is current list of files exhausted? can we create a new
            # file iterator?
            if self.filesList:
                self.matchIterFileObj = MatchIteratorFile(self.filesList.pop())
                continue
    
            # third level: no file iterator, no files list, descend!
            # purposely don't trap exception: StopIterations should bubble up and tell
            # caller that we're done
            (root, subFolder, files) = self.walkObj.next()
    
            for f in files:
                (dummy, ext) = os.path.splitext(f)
                if ext == '.bpgn':
                    self.filesList.append(os.path.join(root, f))

def getFileSystemMatchIterator(path):
    if os.path.isfile(path):
        return MatchIteratorFile(path)
    elif os.path.isdir(path):
        return MatchIteratorDir(path)
    else:
        raise Exception("WTF?")

if __name__ == '__main__':
    gamesCount = 0
    goodGamesCount = 0

    for m in getFileSystemMatchIterator(sys.argv[1]):
        gamesCount += 1

        try:
            m.sanityCheck()
        except MatchMovesOOOException as e:
            print "skipping match due to out of order (or missing) moves", e
            continue
        except MatchZeroMovesException:
            print "skipping match due to it being empty (no moves whatsoever)"
            continue

        m.populateStates()
        print str(m)

        for s in m.states:
            print s

        goodGamesCount += 1
        #raw_input("hit enter for next game")

    print "%d/%d games are good" % (goodGamesCount, gamesCount)
