# coding: utf-8

#-------------------------------------------------------------------------------
# Name:        UPE100 Library
# Purpose:     Provides a high level programmng interface to the
#              UIC UPE-100 CC Payment Device
#
# Author:      David M. Singer (DMS)
#
# Created:     02/27/2018
# Copyright:   (c) DeviceFusion LLC 2018
# License:
#       DeviceFusion LLC CONFIDENTIAL
#
#       [2018] DeviceFusion LLC
#       All Rights Reserved.
#
#       NOTICE:  All information contained herein is, and remains
#       the property of DeviceFusion LLC Incorporated and its suppliers,
#       if any.  The intellectual and technical concepts contained
#       herein are proprietary to DeviceFusion LLC
#       and its suppliers and may be covered by U.S. and Foreign Patents,
#       patents in process, and are protected by trade secret or copyright law.
#       Dissemination of this information or reproduction of this material
#       is strictly forbidden unless prior written permission is obtained
#       from DeviceFusion LLC.
#
#-------------------------------------------------------------------------------


# python modules used by this code
import datetime
import time
import socket
from collections import deque


# sub-strings for UPE100 message parsing and generation
UIC_TRANS_CANCEL_REQ_XML = "<Req><Cmd><CmdId>TxnCancel</CmdId></Cmd></Req>"
UIC_TRANS_SALE_XML_REQ_HEADER = "<Req><Cmd><CmdId>TxnStart</CmdId><CmdTout>000</CmdTout></Cmd><Param><Txn><TxnType>Sale</TxnType><AcctType>Default</AcctType><TxnAmt>"
UIC_TRANS_SALE_XML_REQ_MID = "</TxnAmt><TipAmt></TipAmt><CurrCode>USD</CurrCode><InvoiceId>"
UIC_TRANS_SALE_XML_REQ_FOOTER = "</InvoiceId></Txn></Param></Req>"
UIC_TRANS_VOID_XML_REQ_HEADER = "<Req><Cmd><CmdId>TxnStart</CmdId><CmdTout>0</CmdTout></Cmd><Param><Txn><TxnType>Void</TxnType><TxnId>"
UIC_TRANS_VOID_XML_REQ_FOOTER = "</TxnId></Param></Txn></Req>"
UIC_TRANS_SETTLEMENT_XML_REQ = "<Req><Cmd><CmdId>TxnSettlement</CmdId><CmdTout>0</CmdTout></Cmd></Req>"

# card online authorized and declined transaction result values as per UPE100 documentation
TXN_ACCEPTED = 2
TXN_DECLINED = 3

# states used to track the current command execution
STATE_DOING_NOTHING = 0
STATE_IN_AUTHORIZE = 1
STATE_IN_CANCEL = 2
STATE_IN_VOID = 3


# == Misc. utility functions ================================= #

# get current time from OS
def upe_getnow_ts():
    return (time.time())

# generate the current time as a string
#def upe_timestamp_str():
#    return (datetime.datetime.fromtimestamp(upe_getnow_ts()).strftime('%Y-%m-%d %H:%M:%S'))

# generate the current time as a string as used in UPE command messages
def upe_timestamp_invoice():
    return (datetime.datetime.fromtimestamp(upe_getnow_ts()).strftime('%Y%m%d%H%M%S'))

# check to see if XML received from the UPE is a response message
def upe_is_response(uic_data):
    uic_data = uic_data.strip()
    if uic_data.startswith("<Resp>") and uic_data.endswith("</Resp>"):
        return (True)
    else:
        return(False)
# check to see if XML received from the UPE is an event message
def upe_is_event(uic_data):
    uic_data = uic_data.strip()
    if uic_data.startswith("<Event>") and uic_data.endswith("</Event>"):
        return (True)
    else:
        return(False)

# retrieve the given XML element from the given XML string
def upe_xml_get_element(xml_string, element_string):
    from xml.etree import ElementTree as ET
    formatted_xml = "<?xml version='1.0' encoding='UTF-8'?>" + \
                    "<!DOCTYPE xgdresponse SYSTEM 'xgdresponse.dtd'>" + \
                    "<xgdresponse version='1.0'>" + \
                    xml_string + "</xgdresponse>"

    return(ET.fromstring(formatted_xml.strip()).find(element_string))

# == end of misc. utility functions =================================== #


# == upe100 class definition =========================================== #
# class that provides all of the functionality to connect to the UPE via a socket,
# execute a command and return the command result
class upe100:

    # ============== upe_logger ============ #
    # Function to log informational/debug messages that are generated at runtime.
    # the logging itself is performed via an application specific log function that is called by this function.
    # The application specifies the logger function to call as part of UPE100 object instantiation/creation.
    # There is no default logger function so if the application does not specify one this function simply prints
    # to console
    def upe_logger(self, l_text):
        # if no application level log function is set then just print to console
        if(self.application_logger == None):
            print(l_text)
        else:
            #application level log function is set so call that function to perform logging
            self.application_logger(l_text)
        return
    # ============== upe_logger end ========== #

    # ============== upe_log_persist ========== #
    # This function supplements the upe_logger function. It is used to support selective transaction level logging at the application level.
    # Persisting a logged transaction is performed via an application specific function that is called by this function.
    # The application specifies the logger persistence function to call as part of UPE100 object instantiation/creation.
    # There is no default logger persistence function so if the application does not specify one this function is a NOOP
    #
    # The idea of application level transaction logging is to group a number of individually logged messages
    # into a single delineated transaction in the log. Further the persist function is
    # used to signal the application that it should persist all data (collected only in memory) for its current transaction
    # to disk; this is useful when the application is only logging transactions that have runtime errors rather than all transactions.
    # In the case of error only logging the function should be called whenever an error occurs within this object to enable such peristance.
    def upe_log_persist(self):
        if(self.application_log_persist == None):
            pass
        else:
            self.application_log_persist()
        return
    # ============== upe_log_persist end ========== #

    # ============== open_socket ================== #
    # function to open a socket and connect to the UPE100 device.
    def open_socket(self):
        # try to open the socket at the currently set IP address/Port
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect((self.uic_ip_address, self.uic_port))
        except Exception as e:
            # an error occured in trying to open the socket so log it
            self.upe_logger("open_socket:Error in open_socket: "+str(e))
            self.s = None
        else:
        #    pass
        #finally:
            # Before issuing any commands to the UPE, clear out any commands that it may have been trying to send in
            # response to a prior connection that got interuppted, closed, timeout, etc.
            # probably is never needed but it will ensure that any command issued by the object won't get out of sync.
            # due to responses that are residual from the prior connection
            receive_data = ""
            while(1):
                try:
                    self.s.settimeout(5)
                    receive_data = self.s.recv(4096) # DMS - changed from 2k to 4k. Used 2K in case multiple messages somehow get queued up...
                    if self.log_xml:
                        self.upe_logger("open_socket: Clear read socket - XML_RECEIVE:"+receive_data+":")
                except:
                    self.upe_logger("open_socket: Done clearing socket")
                    break
            return(self.s)
    # ============== open_socket end ================== #

    # ============== close_socket ===================== #
    # function to close the UPE100 device socket.
    def close_socket(self):
        try:
            self.s.close()
        except Exception as e:
            self.upe_logger("close_socket: Error in close_socket: "+str(e))
        #else:
        #    pass
        finally:
            self.s = None
    # ============== close_socket end ================== #

    # ============== split_xml_into_list =============== #
    # this checks the XML received from the UPE to see if it contains multiple UPE messages
    # most of the time only one message will be received per socket read, but not always.
    # in the case where multiple messages are received in the XML, then the XML will be split into
    # distinct messages and accordingly queued for processing.
    def split_xml_into_list(self,xml_data):

        # queue should be empty
        if (len(self.xml_read_queue) <> 0):
            raise Exception ("split_xml_into_list: called with non empty queue, last element: "+self.xml_read_queue[len(xml_read_queue-1)])
        # save raw XML for logging purposses
        log_xml = xml_data

        # proccess the raw XML into one or more queued messages
        while(1):
            if (len(xml_data) == 0):
                break
            # process any response messages in the raw XML
            if (xml_data.startswith("<Resp>")):
                x = xml_data.find("</Resp>")
                self.xml_read_queue.append(xml_data[0:x+7])
                xml_data = xml_data[x+7:len(xml_data)]
            # process any event messages in the raw XML
            elif (xml_data.startswith("<Event>")):
                x = xml_data.find("</Event>")
                self.xml_read_queue.append(xml_data[0:x+8])
                xml_data = xml_data[x+8:len(xml_data)]
            # there is unknown/unsupported XML in the response
            else:
                raise Exception ("split_xml_into_list: xml not event or response: "+xml_data)
        # found multiple messages in the raw XML so log that fact
        if (len(self.xml_read_queue) > 1):
            self.upe_logger("split_xml_into_list: info: queueing multiple data from xml: "+log_xml)

        return (None)
    # ============== split_xml_into_list end ===================== #

    # ============== upe_safe_socket_write ======================= #
    # This function writes the given data to the open UPE socket
    # caller must check return bytes sent <> 0 to confirm that it worked
    # all exceptions trapped and logged.
    def upe_safe_socket_write(self, send_data):

        bytes_sent = 0
        try:
            # write the data to the socket
            # this will always return immidiately
            bytes_sent = self.s.send(send_data.encode(encoding='utf_8', errors='strict'))
            if self.log_xml:
                self.upe_logger("upe_safe_socket_write: "+ send_data)
        except Exception as e:
            self.upe_logger("upe_safe_socket_write: Error- "+str(e))
            bytes_sent = 0
            # DMS ==================================================
            # Since this function performs the low level socket I/O it makes sense to
            # capture at least some socket exceptions and try to handle them here
            # rather them bubble them up to other code, there could be some socket errors that are fatal
            # but the most common would be the UPE forcing a close of the socket,in which case it makes sense
            # to try to restablish the connection and proceed with operation
            self.close_socket() #DMS
            self.open_socket()  #DMS
            # DMS ===================================================
        #else:
        #   pass
        finally:
            return(bytes_sent)
    # ============== upe_safe_socket_write end ================= #

    # ============== upe_safe_socket_read ====================== #
    # This function reads the next XML message from the open UPE socket
    # the function will wait safe_timeout_seconds_or_none_for_blocking seconds
    # before timing out. All exceptions trapped and logged.
    def upe_safe_socket_read(self, safe_timeout_seconds_or_none_for_blocking):

        # If there is already a XML message in the message queue, just return that...
        if (len(self.xml_read_queue) > 0):
            return (self.xml_read_queue.popleft())

        # No messages in the message queue so read one from the socket
        receive_data = ""
        try:
            # read a message from the socket; this will timeout after specified number of seconds
            self.s.settimeout(safe_timeout_seconds_or_none_for_blocking)
            receive_data = self.s.recv(2048) #  Used 2K in case multiple messages some how get queued upin the socket
            if self.log_xml:
                self.upe_logger("upe_safe_socket_read: length="+ str(len(receive_data)) + " :"+ receive_data +":")
            # DMS 062018 - if we successfully recevied 0 length data without any exceptions being raised
            # that indicates that the UPE100 has gracefully closed its end of the socket for some reason
            # so close and reopen the socket and then let the code proceed with a 0 length data return
            # which will be interpreted by the caller as a timeout and processed accordingly
            if (len(receive_data) == 0):
                # log the socket error and persist it
                self.upe_logger("upe_safe_socket_read: got 0 length data, reopening socket")
                self.upe_log_persist()
                # re-establish the socket connection to the UPE100
                self.close_socket()
                self.open_socket()
        except socket.timeout as e:
            # this is a normal timeout on a socket read
            self.upe_logger("upe_safe_socket_read: Warning timeout - "+ str(e))
        except Exception as e:
            # some other socket error so log it and persist it
            self.upe_logger("upe_safe_socket_read: Error - "+ str(e))
            self.upe_log_persist()
            receive_data = ""
            # DMS ==================================================
            # Since this function performs the low level socket I/O it makes sense to
            # capture at least some socket exceptions and try to handle them here
            # rather them bubble them up to other code, there could be some socket errors that are fatal
            # but the most common would be the UPE forcing a close of the socket,in which case it makes sense
            # to try to restablish the connection and proceed with operation
            self.close_socket()
            self.open_socket()
            # DMS ===================================================
        #else:
        #    pass
        finally:
            # received data from the socket which could be one or more XML messages
            # so process the XML into  distinct messages on the message queue
            if (len(receive_data) > 0):
                self.split_xml_into_list(receive_data)
                # now return the first message on the queue
                return(self.xml_read_queue.popleft())
            else:
                # would have to be "" at this point due to timeout or other socket error
                return(receive_data)

    # ============== upe_safe_socket_read end ======= #


    # ============== __init__  ====================== #
    # upe100 object constructor

    def __init__(self,
                 uic_ip_address = '192.168.2.3',    # UPE default IP
                 uic_port = 1000,                   # UPE default port
                 uic_authorize_timeout = 30.0,      # default seconds an authorize will wait for a card insert.
                 uic_in_progress_timeout = 10.0,    # Once a transaction is in a sale (authorize after card inserted, void, cancel), the
                                                    # amount of time it will wait on the UIC.
                 log_file_name = 'upe_cc.log',      # default log file name
                 log_xml = True,                    # flag to log XML data that is processed via socket read and write functions
                 application_logger = None,         # application specified logging function; default is None
                 application_log_persist = None,    # application specified logging persistence support function; default is none
                 ):

        # set object attributes
        self.uic_ip_address = uic_ip_address
        self.uic_port = uic_port
        self.uic_authorize_timeout = uic_authorize_timeout
        self.uic_in_progress_timeout = uic_in_progress_timeout
        self.log_file_name = log_file_name
        self.log_xml = log_xml
        self.application_logger = application_logger # name of function to call to perform logging
        self.application_log_persist = application_log_persist # name of function to call to set persistent logging of transaction data


        # These are transaction states that can be accessed in the callback...
        self.state = STATE_DOING_NOTHING
        self.nfc_allowed = False
        self.magstripe_allowed = False
        self.chip_allowed = False
        self.display_string = "Credit Card Disabled"
        self.event_msg_id = "" # This will hold the code so we can switch to this later instead of text.
        self.event_xml = ""
        self.amount = None
        self.invoice_string = None
        self.txn_result = TXN_DECLINED

        # These are states that can be checked via multi processing or during callback.
        self.reset_transaction_state()

        # This is to hold the socket...set to None when it is closed.
        self.s = None
        # Open the socket to the UPE
        self.s = self.open_socket()

        # This is the timeout that is used in Authorize to handle the long wait after PLEASE SWIPE OR INSERT CARD
        self.authorize_timeout_to_use = None

        # This is for the incoming xml queue...it should normally be empty or have one element unless we get multiple
        # messages in a response from the UPE, the they get placed in this queue and can be popped off...
        self.xml_read_queue = deque()

        # define a dictionary of handler functions for specific UPE events events
        # the dictionary is indexed by the event id that is present in the XML event
        # message sent by the the UPE. Each dictionary entry is composed of three elements.
        # Element 0 : is the event text as it appears in the XML message - this currently
        # has no functional use but help to document which event the entry corresponds to.
        # Element 1 : is the internal object function that is called to process the event
        # after it received from the UPE.
        # Element 2 : is an external application callback function that is called to enable application
        # level processing of the event. The application has to set the callback via
        # this classes emulate_uic_hardware
        self.upe_event_messagestring = 0
        self.upe_event_selfhandlerfunction = 1
        self.upe_event_apphandlerfunction = 2
        # UPE100 event dictionary
        self.upe_events = {
                        "01":["(AMOUNT)",self.handle_noop_event,None],
                        "02":["(AMOUNT) OK?",self.handle_noop_event,None],
                        "03":["APPROVED",self.handle_noop_event,None],
                        "04":["PLEASE CALL YOUR BANK",self.handle_noop_event,None],
                        "05":["CANCEL OR ENTER",self.handle_noop_event,None],
                        "06":["CARD ERROR",self.handle_noop_event,None],
                        "07":["DECLINED",self.handle_noop_event,None],
                        "08":["PLEASE ENTER AMOUNT",self.handle_noop_event,None],
                        "09":["PLEASE ENTER PIN",self.handle_noop_event,None],
                        "10":["INCORRECT PIN",self.handle_noop_event,None],
                        "11":["PLEASE INSERT CARD",self.handle_noop_event,None],
                        "12":["NOT ACCEPTED",self.handle_noop_event,None],
                        "13":["PIN OK",self.handle_noop_event,None],
                        "14":["PLEASE WAIT",self.handle_noop_event,None],
                        "15":["PROCESSING ERROR",self.handle_noop_event,None],
                        "16":["PLEASE REMOVE CARD",self.handle_noop_event,None],
                        "17":["PLEASE USE CHIP CARD",self.handle_usechipcard_event,None],
                        "18":["PLEASE USE MAGSTRIPE CARD",self.handle_usemagcard_event,None],
                        "19":["PLEASE TRY AGAIN",self.handle_noop_event,None],
                        "20":["WELCOME",self.handle_noop_event,None],
                        "21":["PLEASE TAP CARD",self.handle_noop_event,None],
                        "22":["PROCESSING…",self.handle_noop_event,None],
                        "23":["CARD READ OK, PLEASE REMOVE CARD",self.handle_noop_event,None],
                        "24":["PLEASE SWIPE OR INSERT CARD",self.handle_swipeorinsertcard_event,None],
                        "25":["PLEASE PRESENT ONE CARD ONLY",self.handle_noop_event,None],
                        "26":["APPROVED. PLEASE SIGN",self.handle_noop_event,None],
                        "27":["AUTHORIZING. PLEASE WAIT",self.handle_authorization_wait,None], # DMS 03/13/2019
                        "28":["PLEASE TRY ANOTHER CARD",self.handle_noop_event,None],
                        "29":["PLEASE INSERT CARD",self.handle_noop_event,None],
                        "30":["",self.handle_noop_event,None],
                        "31":["",self.handle_noop_event,None],
                        "32":["PLEASE SEE YOUR PHONE FOR INSTRUCTION",self.handle_noop_event,None],
                        "33":["PLEASE TAP CARD AGAIN",self.handle_noop_event,None],
                        "34":["PROCESSING OK",self.handle_noop_event,None],
                        "35":["TRANSACTION REVERSAL",self.handle_noop_event,None],
                        "36":["TRANSACTION DATA UPDATING",self.handle_noop_event,None],
                        "37":["TRANSACTION CANCELED",self.handle_transcancel_event,None],
                        "38":["AUTHORIZATION DEFERRED",self.handle_noop_event,None],
                        "39":["SETTLEMENT PROCESSING",self.handle_noop_event,None],
                        "40":["SYSTEM FILE DOWNLOADING",self.handle_noop_event,None],
                        "41":["SYSTEM UPDATING",self.handle_noop_event,None],
                        "99":["UPE100 DEBUG MESSAGE",self.handle_noop_event,None]
            }

        return(None)
    # ============== __init__  end ================ #

    # ==============  __del__  ====================== #
    # Destructor, explicitly call to close socket

    def __del__(self):
        self.close_socket()
    # ==============  __del__  end =================== #

    # ========= reset_transaction_state  ============ #
    # reset the internal state of this objects' current transaction processing
    def reset_transaction_state(self):
        self.nfc_allowed = False
        self.magstripe_allowed = False
        self.chip_allowed = False
        self.display_string = "Credit Card Disabled"
        self.event_xml = ""
        self.amount = None
        self.invoice_string = None
        return(None)
    # ============== reset_transaction_state end  =============== #

    # ====== set_application_event_callback function  ============ #
    # function that an application uses to set application specific callbacks for UPE100 events
    # input args are:
    # EventMsgId = a string of numeric id of the UPE event (see the upe_events dictionary definition in the
    #               __init__ init function ofr supported event id numbers)
    # EventCallBackFunction = the name of the application function to call. Application callback functions
    # must take a single input argument event_xml. event_xml is the XML event string as received from from the
    # UPE and is passed to the callback to enable the application to further process the event data as needed
    def set_application_event_callbackfunction(self,EventMsgId,EventCallBackFunction):
        try:
            self.upe_events[EventMsgId][self.upe_event_apphandlerfunction]=EventCallBackFunction
        except Exception as e:
            self.upe_logger("set_application_event_callbackfunction:error setting call back function for EventId=" + str(EventMsgId)+ " :" + str(e))
    # ====== set_application_event_callback function  ============ #


    # ================ handle_event =================================== #
    # this function handles events received form the UPE100 by looking the
    # event up in the class' upe_events dictionary and then calling the
    # specific event handler that is set in the dictionary for the event
    # event handler calling is a two step process:
    # step 1: the class' internal event handler for the specific event is called
    # step 2: if set in the dictionary the application specifc calback for the event is called
    def handle_event(self, event_xml):

        # DMS 03242018 - use this time out for everything except "enter card
        # Enter card event in event handler will update to the authorize timeout
        self.authorize_timeout_to_use = self.uic_in_progress_timeout
        # Here we infer some things based on the text in the event before calling the
        # callback...
        event_text = upe_xml_get_element(event_xml,'Event/Type/ReqDispMesg/MesgStr').text
        event_msg_id = upe_xml_get_element(event_xml,'Event/Type/ReqDispMesg/MesgId').text
        self.display_string = event_text
        self.event_msg_id = event_msg_id
        self.event_xml = event_xml

        # look up which intenral class event handler function to call for this event in the dictionary and call it.
        self.upe_events[event_msg_id][self.upe_event_selfhandlerfunction](event_xml)
        # next lookup to see if there there is an application function that is set for this event
        # and if so call it
        if(self.upe_events[event_msg_id][self.upe_event_apphandlerfunction] != None):
            self.upe_events[event_msg_id][self.upe_event_apphandlerfunction](event_xml)

        return(None)
    # ================ handle_event end =================================== #


    # ********************************************************************* #
    # == class' internal UPE100 event handlers ============================ #
    # The following set of functions are the
    # class' internal UPE 100 event handler definitions ===== #
    # the call to these functions is set in the upe_events
    # callback dictionary

    # ============== handle_transcancel_event  ================== #
    # event handler for the UPE100 "37":"TRANSACTION CANCELED" event
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_transcancel_event(self,event_xml):
        self.reset_transaction_state()
        # unfortunately, have to reset these so they are available....
        event_text = upe_xml_get_element(event_xml,'Event/Type/ReqDispMesg/MesgStr').text
        self.display_string = event_text
        self.event_xml = event_xml
    # ============== handle_transcancel_event end ================ #

    # ============== handle_swipeorinsertcard_event  ============= #
    # event handler for the UPE100 "24":"PLEASE SWIPE OR INSERT CARD" event
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_swipeorinsertcard_event(self,event_xml):
        self.authorize_timeout_to_use = self.uic_authorize_timeout # For the longer wait.
        self.nfc_allowed = False
        self.magstripe_allowed = True
        self.chip_allowed = True
    # ============== handle_swipeorinsertcard_event end  ========== #

    # ============== handle_usechipcard_event  ===================== #
    # event handler for the UPE100 "17":"PLEASE USE CHIP CARD" event
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_usechipcard_event(self,event_xml):
        self.nfc_allowed = False
        self.magstripe_allowed = False
        self.chip_allowed = True
    # ============== handle_usechipcard_event end =================== #

    # ============== handle_usemagcard_event  ======================= #
    # event handler for the UPE100 "18":"PLEASE USE MAGSTRIPE CARD" event
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_usemagcard_event(self,event_xml):
        self.nfc_allowed = False
        self.magstripe_allowed = True
        self.chip_allowed = False
    # ============== handle_usemagcard_event end ==================== #

    # ============== handle_authorization_wait  ======================= #
    # event handler for the UPE100 "27":"AUTHORIZING. PLEASE WAIT" event
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_authorization_wait(self,event_xml):
        #time.sleep(15) # DMS 05022019 disabled wiat b/c of new UPE firmware timeouts ,DMS 03/13/2019 - UPE is busy processing so give it some more time
        pass

    # ============== handle_authorization_wait end ==================== #

    # ============== handle_noop_event  ============================= #
    # default UPE event handler called for all events that are not currently
    # supported or need explicit internal processing by the class
    # This function is set as the default internal event handler in the
    # upe_events dictionary definition
    def handle_noop_event(self,event_xml):
        self.upe_logger("Handing for this event is a NOOP:" + event_xml)
    # ============== handle_noop_event end ========================== #

    # == end of class' internal UPE 100 event handler definitions ===== #
    # ***************************************************************** #


    # ********************************************************************* #
    # ==  UPE100 commands that are currently supported by the class ======= #
    # below are functions an application can call to execute UPE100 commands
    # these are the ony UPE100 commands currentlysupported by the class

    # ============== cancel_transaction  ============================= #
    # function the application calls to send the UPE100 a cancel command
    def cancel_transaction(self):

        # update internal state
        self.state = STATE_IN_CANCEL
        self.reset_transaction_state()

        # send the UPE100 Cancel command
        bytes_written = self.upe_safe_socket_write(UIC_TRANS_CANCEL_REQ_XML)
        if (bytes_written == 0):
            # failed to send the command to the UPE
            raise Exception ("Failed to write transaction cancel")
        else:
            # command was sent OK, so now wait for and process the UPE100 response
            while(1):
                response = self.upe_safe_socket_read(self.uic_in_progress_timeout)
                if len(response)  == 0:
                    self.upe_logger("cancel_transaction: Warning got timeout")
                    #DMS 03052018 D rev.
                    #break
                    # did not get a reponse from the UPE100 wihtin the specified timeout period
                    raise Exception ("cancel_transaction: Got timeout")
                    #DMS 03052018 D rev.
                # got a response form the UPE so process it accordingly
                if (upe_is_event(response) == True):
                    self.handle_event(response)
                elif (upe_is_response(response) == True):
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code != "0000"):
                        raise Exception ("cancel_transaction: returned invalid code: "+status_code+", xml:"+ response)
                    break
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    raise Exception ("cancel_transaction: Bad xml: "+ response)

        self.upe_logger("cancel_transaction: Transaction successfully cancelled")
        return(None)

    # ============== cancel_transaction end ========================== #

    # ============== authorize ======================================= #
    # function the application calls to send the UPE100 a Sale command
    # amount is a text string of the sale amount, e.g '1.00' = $1.00
    # invoice_string can be blank, then it will be derived from the date.
    def authorize(self, amount, invoice_string = None):

        # update internal state
        self.state = STATE_IN_AUTHORIZE
        if invoice_string == None:
            invoice_string = upe_timestamp_invoice()

        self.invoice_string = invoice_string
        self.amount = amount

        # send the UPE100 the Sale command
        self.upe_logger("authorize: for invoice: "+ invoice_string)
        xml_sale_request = UIC_TRANS_SALE_XML_REQ_HEADER + amount + \
                           UIC_TRANS_SALE_XML_REQ_MID + invoice_string + \
                           UIC_TRANS_SALE_XML_REQ_FOOTER

        bytes_written = self.upe_safe_socket_write(xml_sale_request)
        # failed to send the command to the UPE100 so raise an exception
        # to be caught by the application
        if bytes_written == 0:
            raise Exception("authorize: write failed")


        # now read all events/command responses from the UPE100
        #
        # set the timeout for waiting for a UPE response
        # This gets it through the loop below the first time
        # then changed to authorize timeout in the event handler.
        self.authorize_timeout_to_use = self.uic_in_progress_timeout
        retcode = False
        while(1):

            self.upe_logger( "authorize: timeout="+ str(self.authorize_timeout_to_use))
            response = self.upe_safe_socket_read(self.authorize_timeout_to_use)
            if (response == ""): # Timeout reached...
                # DMS =================================================
                # if in authorize state (!STATE_IN_CANCEL) then execute the cancel command AND continue reading
                # responses from the UPE because a Sale command response should be comming next and will be handled below
                # if that response does not arrive in subsequent read AND the cancel command was issued then
                # just break out of the loop and return a failed return code because the socket or UPE is not repsonding
                # with anything
                if (self.state == STATE_IN_CANCEL):
                    # if we previously issued the cancel command but got no addtional responses to close out the
                    # current Sale comand then just fail
                    break
                else:
                    # we expected to read either the next intermediate event from the Sale command
                    # or the final Sale command response, neither occured with the set time out
                    # so cancel the transaction and continue because we are expecting the final response to the Sale comand
                    # after this cancel is issued
                    self.cancel_transaction()
                    break #DMS 03052015 "D version firmware / no SaleCmd response on cancel
                #DMS =====================================================
            else:
                # Presumably in transaction....
                if (upe_is_response(response)):
                    self.event_xml = "" # not an event
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code != "0000"):
                         # raise an exception if code is not zero; this will be caught in the application
                         raise Exception ("authorize:  returned invalid code: "+ status_code+", xml:"+ response)
                    else:
                        # Got the response to the Sale command with a success (0) retrun code
                        # DMS =======================================================
                        # in reading the UPE documentation there may be other non-zero retrun codes that
                        # might also be considnered successful - TBD!
                        # DMS ========================================================
                        self.last_transaction_id = upe_xml_get_element(response,'Resp/Data/Txn/TxnId').text
                        #
                        # the command executed with success but now have to get the transaction result
                        self.txn_result = TXN_DECLINED
                        txnres_string = upe_xml_get_element(response,'Resp/Data/Txn/TxnResult').text
                        try:
                            txnres = int(txnres_string)
                        except:
                            txnres = TXN_DECLINED
                        if(txnres == TXN_ACCEPTED):
                            self.txn_result = TXN_ACCEPTED
                        # regardless of the tranaction accept/decline result the command successfully executed so return true
                        retcode=True
                        break
                elif (upe_is_event(response)):
                    # got an intermediate Sale command event prior to the final Sale command response
                    self.handle_event(response)
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    raise Exception ("authorize: Bad xml - "+ response)

        # return the command result
        return(retcode)
    # ============== authorize end =================================== #



    # ============== void_transaction ============================= #
    # function the application calls to send the UPE100 a Void command
    #  void an open transaction, defaults to the last one
    #  Call before settle_transasction to undo a sale.
    #  invoice_string can be blank, then it will default to the last invoice used.
    def void_transaction(self, transaction_id = None):

        # update internal state
        self.state = STATE_IN_VOID
        self.reset_transaction_state()
        if (transaction_id == None):
            transaction_id = self.last_transaction_id

        # send the Void command to the UPE100
        bytes_written = self.upe_safe_socket_write(UIC_TRANS_VOID_XML_REQ_HEADER + transaction_id +  UIC_TRANS_VOID_XML_REQ_FOOTER)
        if (bytes_written == 0):
            # sending of the command failed, so raise an exception to be caught by the application
            raise Exception ("void_transaction: write failed")
        else:
            # now get and process all events and responses from the UPE100
            while(1):
                response = self.upe_safe_socket_read(self.uic_in_progress_timeout)
                if len(response)  == 0:
                    self.upe_logger("void_transaction: Warning got timeout")
                    break
                if (upe_is_event(response) == True):
                    self.handle_event(response)
                elif (upe_is_response(response) == True):
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code != "0000"):
                        raise Exception ("void_transaction:  returned invalid code: "+status_code+", xml:"+response)
                    break
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    raise Exception ("void_transaction: Bad xml in void_transaction(): "+ response)

        self.upe_logger("void_transaction: Transaction: "+transaction_id+" successfully voided")

        return(True)
    # ============== void_transaction end ============================= #


    # ============== audible_alert ============================= #
    # function the application calls to send the UPE100 an AudibleAlarm command
    # This function uses the enunciator on the UPE100 to cause an audible signal to the user
    def audible_alert(self,alarm_count="3",alarm_duration="250",alarm_interval="250", wait_time=30):

        retval = False
        # send the command to the UPE100
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>SystemMgmt</CmdId><CmdTout>5</CmdTout></Cmd><Param><Sys><Id>AudibleAlarm</Id>" + \
                                                    "<AlarmCount>" + alarm_count + "</AlarmCount><AlarmDuration>" + alarm_duration +  "</AlarmDuration>" + \
                                                    "<AlarmInterval>" + alarm_interval + "</AlarmInterval></Sys></Param></Req>")
        if (bytes_written == 0):
            # sending the command failed but this is a non-critical
            # function so do nothing but return a False return value
            pass
        else:
            # comand was sent so wait for and process the response.
            response = self.upe_safe_socket_read(wait_time)
            if len(response)  == 0:
                # did not get a reponse from the UPE so just log it and return False result
                self.upe_logger("audible_alert: Warning got timeout waiting for command response")
            else:
                # command executed ok
                retval = True
        return(retval)
    # ============== audible_alert end ========================== #

    # ============== check_cc_inserted ============================= #
    # function the application calls to test  if the Chip Card is still
    # inserted in the reader --
    # A True return value inidcates the user left the Chip Card inserted in the reader
    def check_cc_inserted(self,wait_time=30):
        retval = False
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>DiagMgmt</CmdId><CmdTout>20</CmdTout></Cmd>" + \
                                                    "<Param><Diag><Id>TestICCPresence</Id></Diag></Param></Req>")
        if (bytes_written == 0):
            self.upe_logger("check_cc_inserted: could not write command to UPE100 socket")
            # even though the sending of the command to the UPE failed
            # this is not a critical function so assume the card is not inserted and return a status to indicate that
            retval = False
        else:
            response = self.upe_safe_socket_read(wait_time)
            if len(response)  == 0:
                self.upe_logger("check_cc_inserted: Warning got timeout waiting for TestICCPresence command reponse")
                retval = False
            else:
                try:
                    # got a response string so extract the CC insert status from it
                    idx = response.find("Chip Card Inserted")
                    if(idx == -1):
                        self.upe_logger("check_cc_inserted:card not inserted")
                        # the â€œChip  Card  Insertedâ€ string is not in the repsonse so that indicates the card is not inserted
                        retval = False
                    else:
                        # the Chip  Card  Insertedâ string is in the respone o that indicated the card is inserted
                        self.upe_logger("check_cc_inserted:card left inserted")
                        retval = True
                except Exception as e:
                    # something went wrong in checking the response and because this is not a critical function
                    #then just assume the card is not inserted
                    self.upe_logger("check_cc_inserted:Got an exception when checking command response" + str(e))
                    retval = False
        return(retval)
    # ============== check_cc_inserted end ===================== #

    # ============== reboot_system ============================= #
    # function the application calls to reset the UPE100
    # This function reboots the UPE100 and then sleeps for the specified time to allow the UPE to boot up
    def reboot_system(self,wait_time=30):
        retval = False
        # send the reboot command to the UPE100
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>SystemMgmt</CmdId><CmdTout>5</CmdTout></Cmd>" + \
                                                    "<Param><Sys><Id>RebootSystem</Id></Sys></Param></Req>")

        if (bytes_written == 0):
            # the write failed but this is a non-critical function so do nothing
            # but return a False return code
            pass #raise Exception ("Failed to write transaction void")
            return(retval)
        else:
            # command was sent so now wait for the response for the given wait_time.
            response = self.upe_safe_socket_read(wait_time)
            if len(response)  == 0:
                # did not get a response within the timeout period so return Flase
                self.upe_logger("reboot_system: Warning got timeout")
            else:
                # got response from UPE
                retval = True

        # now sleep for a bit to give the UPE100 time to to boot up again
        time.sleep(wait_time)
        return(retval)
    # ============== reboot_system end ============================= #

    # ============== update_firmware ============================= #
    # function the application calls to update the UPE100 firmware
    # This function updates the UPE100 firmware and then sleeps for the specified time to allow the UPE to boot up
    def update_firmware(self, wait_time):

        retval = False
        # send the update command to the UPE100
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>SystemMgmt</CmdId><CmdTout>0</CmdTout></Cmd>" + \
                                                    "<Param><Sys><Id>UpdateSysProgram</Id></Sys></Param></Req>")

        if (bytes_written == 0):
            # the write failed but this is a non-critical function so do nothing
            # but return a False return code
            pass #raise Exception ("Failed to write transaction void")
            self.upe_logger("update_firmware: failed to write UpdateSysProgram command to UPE")
            return(retval)
        else:
            # command was sent so now wait for the response for the given wait_time.
            while(1):
                response = self.upe_safe_socket_read(wait_time)
                if len(response)  == 0:
                    self.upe_logger("update_firmware: : Warning got timeout waiting for response")
                    #return(retval)
                    break
                if (upe_is_response(response) == True):
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code == "FF13"):
                        # system needs updating FF13
                        self.upe_logger("update_firmware: : system needs updating FF13 response")
                    elif (status_code == "0000"):
                        # system is up to date 0000 response
                        self.upe_logger("update_firmware: : system is up to date 0000 response")
                        return(True)
                    elif (status_code == "FF11"):
                        # system needs updating FF11
                        self.upe_logger("update_firmware: : timeout FF11 response")
                        break
                    else:
                        # unexpected response code
                        self.upe_logger("update_firmware: : unexpected response code" + status_code)
                        return(retval)
                elif (upe_is_event(response) == True):
                    msgid = upe_xml_get_element(response,'Event/Type/ReqDispMesg/MesgId').text
                    self.handle_event(response)
                    if (msgid == "40"):
                        self.upe_logger("update_firmware: : msg 40 - system update file is downloading")
                    elif (msgid == "15"):
                        self.upe_logger("update_firmware: : msg 15 - processing error")
                        break
                    elif (msgid == "41"):
                        self.upe_logger("update_firmware: : msg 41 - download successful - system updating")
                        # UIC update docs says wait 60 seconds before proceeding, ths is set to 90 for safety
                        time.sleep(90)
                        return(True)
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    self.upe_logger("update_firmware: : unexpected response not an event or response" + status_code)
                    #return(retval)
                    break

        # update failed mid process so reboot the UPE
        self.reboot_system(wait_time=45)
        return(retval)
    # ============== update_firmware end ============================= #

    # ============== get_system_time ============================= #
    # function the application calls to update the UPE100 firmware
    # This function updates the UPE100 firmware and then sleeps for the specified time to allow the UPE to boot up
    def get_system_time(self):

        self.upe_log_persist()

        retval = False
        # send the get time command to the UPE100
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>InfoMgmt</CmdId><CmdTout>0</CmdTout></Cmd>" + \
                                                    "<Param><Info><Id>GetSystemTime</Id></Info></Param></Req>")

        if (bytes_written == 0):
            # the write failed but this is a non-critical function so do nothing
            # but return a False return code
            #pass #raise Exception ("Failed to write transaction void")
            self.upe_logger("get_system_time: failed to write GetSystemTime command to UPE")
            return(retval)
        else:
            # command was sent so now wait for the response for the given wait_time.
            while(1):
                response = self.upe_safe_socket_read(30)
                if len(response)  == 0:
                    self.upe_logger("get_system_time: Warning got timeout waiting for response")
                    #return(retval)
                    break
                if (upe_is_response(response) == True):
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code == "0000"):
                        self.upe_logger("get_system_time response:" + response)
                        return(True)
                    else:
                        # unexpected response code
                        self.upe_logger("get_system_time: non-zero status code" + status_code)
                        return(retval)
                elif (upe_is_event(response) == True):
                    msgid = upe_xml_get_element(response,'Event/Type/ReqDispMesg/MesgId').text
                    self.handle_event(response)
                    self.upe_logger("get_system_time: got event "+ msgid)
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    self.upe_logger("get_system_time: unexpected response not an event or response" + status_code)
                    #return(retval)
                    break

        return(retval)
    # ============== get_system_time end ============================= #

    # ============== get_peripheral_time ============================= #
    # function the application calls to update the UPE100 firmware
    # This function updates the UPE100 firmware and then sleeps for the specified time to allow the UPE to boot up
    def get_peripheral_time(self):

        self.upe_log_persist()

        retval = False
        # send the get time command to the UPE100
        bytes_written = self.upe_safe_socket_write("<Req><Cmd><CmdId>InfoMgmt</CmdId><CmdTout>0</CmdTout></Cmd>" + \
                                                    "<Param><Info><Id>GetPeripheralTime</Id></Info></Param></Req>")

        if (bytes_written == 0):
            # the write failed but this is a non-critical function so do nothing
            # but return a False return code
            #pass #raise Exception ("Failed to write transaction void")
            self.upe_logger("get_peripheral_time: failed to write GetPeripheralTime command to UPE")
            return(retval)
        else:
            # command was sent so now wait for the response for the given wait_time.
            while(1):
                response = self.upe_safe_socket_read(30)
                if len(response)  == 0:
                    self.upe_logger("get_peripheral_time: Warning got timeout waiting for response")
                    #return(retval)
                    break
                if (upe_is_response(response) == True):
                    status_code = upe_xml_get_element(response,'Resp/Cmd/StatusCode').text
                    if (status_code == "0000"):
                        self.upe_logger("get_peripheral_time response:" + response)
                        return(True)
                    else:
                        # unexpected response code
                        self.upe_logger("get_peripheral_time: non-zero status code" + status_code)
                        return(retval)
                elif (upe_is_event(response) == True):
                    msgid = upe_xml_get_element(response,'Event/Type/ReqDispMesg/MesgId').text
                    self.handle_event(response)
                    self.upe_logger("get_peripheral_time: got event "+ msgid)
                else:
                    # Not an event and not a response -- two xml's in one socket read?
                    self.upe_logger("get_peripheral_time: unexpected response not an event or response" + status_code)
                    #return(retval)
                    break

        return(retval)
    # ============== get_peripheral_time end ============================= #

    # ********************************************************************* #
    # ==  end of UPE100 command functions ================================= #
#
#
# == end of upe100 class definition ====================================== #



