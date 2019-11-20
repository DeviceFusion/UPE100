#-------------------------------------------------------------------------------
# Name:        Payment Manager
# Purpose:
#
# Author:      Dave
#
# Created:     13/03/2014
# Copyright:   (c) Dave 2014
# Licence:     <your licence>
#-------------------------------------------------------------------------------
"""
This module is responsible for all functions related to user payments.
This includes recognizing a user has swiped their CC through the reader,
reading the user's CC data from the reader, the authorization and cancelling
of payment with the third party acquirer, handling all associated errors,
and generating all high level events required by the high level machine control.
This module provides a programming interface to initiate transaction to
authorize and cancel payments with the third party acquirer, and an interface
to retrieve error codes that may result from such transactions.

Master Control Events
E1: Card Swipe
This event signals that a user has swiped their credit card
through the magnetic card reader, and the CC data has been read
and is ready for processing.

E2: Card Authorized
This event signals that the user's CC has been successfully
authorized through the third party acquirer,
and as a result payment for the K-cup has been made.


E10:Authorization Error
This event signals that the user's CC authorization through the third
party acquirer has failed and as a result, payment for the K-cup
has not been made.  Failure to authorize could be due to the card being
rejected by the acquirer or other errors such as communication failures.


"""

def main():
    pass

if __name__ == '__main__':
    main()


import threading
import time

#import logger object from config file
from kk_logger import kklog

# import the fsm event queue
from config import fsm_event_queue
# import the fsm error queue
from config import fsm_error_queue

# this module executes a thread so import the thread run control flag
#from config import thread_run_flag
from config import GetThreadRunFlag

# import the KK fsm event definitions
from config import e_cardswipe
from config import e_authorized
from config import e_authorization_err

# this module uses the UPE100 IP address from the config file
# import function to look up configruation key=value values
# from the configuration data dictionary
from config import GetConfigurationValue
#'<uic_ip_address>'



# import function to see what mode to use:emulation or actual BBB hardware
from config import RunBBBHW

#import function to update the display with swipe and authorization
# user instruction and status messages
# to use put the display message(s) strings in an array and pass
# the array as an argument.
# to add error messages put the error messages on the fsm_error_queue prior to calling the UpdateDisplay function
# aand then call UpdateDisplay with the message text value "<errorqueue>" in the array argument.
from display_manager import UpdateDisplay

#import the UPE100 CC reader Object
#from mpc_cc1_v2 import mpc_cc
#from mpc_cc1_v2 import TXN_ACCEPTED
from UPE100 import upe100
from UPE100 import TXN_ACCEPTED

# to test get the kk hw emulator objects
import kk_hw_emulator


import sys

# create an event to signal when the CC authrozation can proceed
from config import CARD_WAIT_TIME
proceed_with_authorization_event = threading.Event()
# create an event to signal when the CC reader should be polled
poll_for_cc_read_event = threading.Event()

# define supported reader types all derived from a generic reader type
class GenericReader:

    def __init__(self):
        self.SaleIsApproved = False
        self._ErrorMsg = ""
        self.SalePrice =  GetConfigurationValue('<sale_price>')
        # make sure a valid sale price was in the configuration; if it is not valid the
        # configuration key vlaue is returned instead
        if(self.SalePrice == '<sale_price>'):
            self.SalePrice = 0.0

    # detects a card swipe - for this generic object just return nothing read
    # the method defintion allows default behavior
    def DetectCardRead(self):
        return false
    # process the data from a card read - for this generic object this is a null operatiion
    # the method defintion allows default behavior
    def ProcessCardRead(self):
        pass

    # For the genric reader this is a NOOP. Keep this a NOOP to force any given reader type
    # to define a reader specific Authorization method.
    def AuthorizeCC(self):
        pass

    def VoidCC(self):
        pass

    def GetReaderErrorMsg(self):
        ErrorMsg = self._ErrorMsg
        self._ErrorMsg = ""
        return(ErrorMsg)

    def SetReaderErrorMsg(self, Errormsg):
        self._ErrorMsg = Errormsg


    def EmulateAuthorization(self):
        import random
        #authorization failure messages for test/emulation purposes only
        authfailmessage = 'Credit card declined', 'Communication time out'
        # emulate the authorization by
        # sleeping for some time and generate a return event
        self.SaleIsApproved = True
        time.sleep(2)
        err_reason = ""
        autheventindex = random.randint(0, 19)
        if autheventindex < 2 : # 10% of the time retrun auth error
            self.SaleIsApproved = False
            err_reason = authfailmessage[autheventindex]
            self.SetReaderErrorMsg(err_reason)

    def EmulateVoid(self):
        # emulate the cancel transaction
        # by sleeping for some time and generate a random return event
        authfailmessage = 'Invalid transaction id', 'Communication time out'
        time.sleep(3)
        # gen a random return event
        import random
        err_reason = ''
        auth_error = False
        autheventindex = random.randint(0, 19)
        if autheventindex < 2 : # 10% of the time return auth error
            auth_error = True
            err_reason = authfailmessage[autheventindex]
            self.SetReaderErrorMsg(err_reason)

        return auth_error

    # generic function to check to see if a card
    # is currently inserted into the reader
    # for magnetic swipe card readers the card can;t be left in by definition
    # for chip card insert readers just assume a genric default of "not left in the reader"
    # so always returns false
    def CardInserted(self):
        return(False)

    # genric function to use the "reader's" enunciator to audibly alert the user
    def AudibleAlert(self):
    # running on BBB Hardware then use it's audio output
        if RunBBBHW():
            pass
        else:
            # no using hardware so try to
            # emulate the piezo buzzer
            # by using the windows audio library instead
            try:
                import winsound
                Freq = 2500 # Set Frequency To 2500 Hertz
                Dur = 500 # Set Duration To 1000 ms == 1 second
                winsound.Beep(Freq,Dur)
            except ImportError:
            # no windows sound module
                pass
        return(True)

    # generic function to reboot the "reader"
    # as a genric default just sleep the specified amount of time
    def RebootReader(self,wait_time=30):
        time.sleep(wait_time)
        return(True)

    def UpdateFirmware(wait_time=120):
        time.sleep(wait_time)
        return(True)






class Emulation_Reader(GenericReader):

    def DetectCardRead(self):
        time.sleep(1)
        swiped=False
        gpio = kk_hw_emulator.GPIO(kk_hw_emulator.ccswipeid)
        if gpio[0]: # if true card swiped
            swiped=True
            #fsm_event_queue.append(e_cardswipe)
        return(swiped)

    def AuthorizeCC(self):
        self.EmulateAuthorization()

    def VoidCC(self):
        self.EmulateVoid()



class UPE100_Reader(GenericReader):

    def __init__(self):
        GenericReader.__init__(self)

        self.RemoveCardMsg = "Remove card and retry"

        # get the IP address and port as configured in the ini file
        # also make sure a valid ip addr:port  in the configuration; if it is not valid the
        # configuration key value is returned instead: so use UPE100 factory IP and port
        UPE100_ip_addr =  GetConfigurationValue('<uic_ip_address>')
        if(UPE100_ip_addr == '<uic_ip_address>'):
            UPE100_ip_addr = '192.168.2.3'
        try:
            UPE100_ip_port = int(GetConfigurationValue('<uic_port>'))
        except:
            UPE100_ip_port = 1000
        kklog.append( UPE100_ip_addr + ":" + str(UPE100_ip_port))

        # create a UPE100 reader object and connect to it at the given IP address:port
        self.UPE100 = upe100(uic_ip_address = UPE100_ip_addr,uic_port=UPE100_ip_port,uic_authorize_timeout=43200.0, uic_in_progress_timeout =45.0, log_xml = True, \
         application_logger = kklog.append,application_log_persist=kklog.persist_transaction )

        # setup UPE100 event call backs
        '''
        # setup the UPE100 event call backs


        # robotic inserter events for automated testing
        inserter = robotic_inserter(port_val='COM9',insertfreq_val=10, inserttime_val=45)
        self.UPE100.set_application_event_callbackfunction("24",inserter.insertcc)
        self.UPE100.set_application_event_callbackfunction("16",inserter.removecc)
        self.UPE100.set_application_event_callbackfunction("15",inserter.removecc)
        self.UPE100.set_application_event_callbackfunction("28",inserter.removecc)
        '''
        # Events generated by a UPE100 normal Sale command
        #event order from an actual success full read
        #<MesgId>24</MesgId><MesgStr>PLEASE SWIPE OR INSERT CARD</MesgStr>
        #<MesgId>14</MesgId><MesgStr>PLEASE WAIT...</MesgStr>
        #<MesgId>16</MesgId><MesgStr>PLEASE REMOVE CARD</MesgStr>
        #<MesgId>27</MesgId><MesgStr>AUTHORIZING. PLEASE WAIT...</MesgStr>
        #self.UPE100.set_application_event_callbackfunction("24",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("14",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("16",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("27",self.UPE100_EventHandler)
        # Events generated by a UPE100 error during a Sale command
        # events from a bad card read??
        #"15":"PROCESSING ERROR"
        #"28":"PLEASE TRY ANOTHER CARD"
        #self.UPE100.set_application_event_callbackfunction("15",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("15",self.ProcessingError_EventHandler)
        self.UPE100.set_application_event_callbackfunction("28",self.UPE100_EventHandler)

        # Mag cards are not supported so call special event handler to nullifly the
        # request to insert the mag card by canceling the current sale
        # "18":"PLEASE USE MAGSTRIPE CARD"
        self.UPE100.set_application_event_callbackfunction("18",self.MagCardCCNullify_EventHandler)


        # event handler for Void transaction events
        #<Event><MesgId>36</MesgId><MesgStr>TRANSACTION DATA UPDATING...</MesgStr></Event>
        #<Event><MesgId>34</MesgId><MesgStr>PROCESSING OK</MesgStr></Event>
        self.UPE100.set_application_event_callbackfunction("36",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("34",self.UPE100_EventHandler)

        # event handler for UPE100 system firmware update process
        # 40 = file downloading, 41 = system updating
        self.UPE100.set_application_event_callbackfunction("40",self.UPE100_EventHandler)
        self.UPE100.set_application_event_callbackfunction("41",self.UPE100_EventHandler)

        self.LastEventmessage=""

        # update UPE100 system firmware if configured to do so
        update_firmware = GetConfigurationValue('<uic_update_firmware>')
        if  update_firmware == '1':
            UpdateDisplay(["Updating reader firmware", "Please wait 5 minutes"])
            res=self.UpdateFirmware()
            if(res == True):
                UpdateDisplay(["Reader firmware completed update"])
            else:
                UpdateDisplay(["Reader firmware update failed"])
            self.AudibleAlert()

        self.UPE100.get_system_time()
        self.UPE100.get_peripheral_time()



    #function to see if the card is currently inserted into the reader
    def CardInserted(self):
        return(self.UPE100.check_cc_inserted())


    # application callable function to use the reader's enunciator to audible alert the user
    def AudibleAlert(self):
        res = self.UPE100.audible_alert("2","250","250")
        return(res)

    # application callible function to reboot the UPE100
    def RebootReader(self,wait_time=30):
        res = self.UPE100.reboot_system(wait_time)
        return(res)
    # perform a system firmware update of the UPE100
    def UpdateFirmware(self, wait_time=300):
        res = self.UPE100.update_firmware(wait_time)
        return(res)




    def __del__(self):
        del(self.UPE100)

    # Detect a card swipe from the reader
    # ****** IMPORTANT NOTE ******
    # For the UPE100 this actually performs the entire cycle sales cycle
    # 1. Executes a UP100 Sale command
    # 2. Receives intermediate events from the UPE100 and forwards then to this object via callbacks that are
    #    set in this object's __init__ method
    # 3. Actually performs the CC authorization with the thrid party authorizer <<< this step is important to note
    #   because unlike a mag card, once the function retruns there is nothing else to do. Therefore
    #   the subsequent ExecuteAuthorizationCCState function that is called by the FSM to execute the authorize state of the main FSM
    #   becomes a NOOP (uses the base class GenericReader.Authorize method) for the UPE100
    def DetectCardRead(self):
        # Do a Start Sale Transaction to the UIC
       retval=False

       try:
            # execute the next sale/authorize command and print return status
            self.UPE100.get_system_time()
            self.UPE100.get_peripheral_time()

            if self.UPE100.authorize(self.SalePrice):
                # a card was swiped and authorized so process accordingly
                if(self.UPE100.txn_result == TXN_ACCEPTED):
                    self.SaleIsApproved=True
                    retval=True
                    kklog.append("DetectCardRead:Authorization Approved")
                else:
                    kklog.append("DetectCardRead: Authorization Declined")
                    self.SetReaderErrorMsg("Card Declined")
                    self.SaleIsApproved=False
                    retval=True
            else:
                # no card was presented in the current Sale cycle
                kklog.append("DetectCardRead:No card in sale cycle")
                self.SaleIsApproved=False
       except Exception as e:
            # some exception occured durng the current sale cycle
            kklog.append("DetectCardRead: Authorization Got An Exception  " + str(e))
            kklog.persist_transaction()
            self.SetReaderErrorMsg(self.LastEventmessage)
            self.SaleIsApproved=False
            retval=True
       return retval

    def UPE100_EventHandler(self,xml_msg):
        # update display with this events text??
        #  # update the display with the messages for this state
        # display_manager.UpdateDisplay([<event_message_text>])
        self.LastEventmessage=self.UPE100_GetEventText(xml_msg)
        UpdateDisplay([self.LastEventmessage])

    def UPE100_GetEventText(self,xml_msg):
        from xml.etree import ElementTree as ET
        try:
            formatted_xml = "<?xml version='1.0' encoding='UTF-8'?>" + \
                        "<!DOCTYPE xgdresponse SYSTEM 'xgdresponse.dtd'>" + \
                        "<xgdresponse version='1.0'>" + \
                        xml_msg + "</xgdresponse>"
            kklog.append(ET.fromstring(formatted_xml.strip()).find('Event/Type/ReqDispMesg/MesgStr').text)
            return(ET.fromstring(formatted_xml.strip()).find('Event/Type/ReqDispMesg/MesgStr').text)
        except:
            return("UPE100_GetEventText- error extracting message string")
        #event_text = mpc_xml_get_element(event_xml,'Event/Type/ReqDispMesg/MesgStr').text


     # Mag cards are not supported so define special event handler to nullify the
     # UPE100 user request to insert the mag card. The Null is accomplished by canceling the current sale
     # command and then rasing an exception to signal an authorization error
    def MagCardCCNullify_EventHandler(self,xml_msg):

       try:
            # got a chip card read error and a use mag card event;
            # mag cards are not supported so just cancel the sale
                self.UPE100.cancel_transaction()
                self.LastEventmessage = self.RemoveCardMsg
                kklog.append("NullMagCard:successfully cancelled sale")
       except Exception as e:
                kklog.append("MagCardCCNullify_EventHandler: Got an exception" + str(e))
                kklog.persist_transaction()
                self.LastEventmessage("NullMagCard: Cancel transaction failed")
       # this routine is essentially handling a user error condition of
       # not inserting the card correctly, so signal this to the DetectCardRead member function by throwing an
       # exception that it will hanlde as an authorization error
       raise Exception ("NullMagCard:Processing Error")

    # UPE100 processing error seem to be fatal to its operation so reboot it if one occurs
    #DMS11272018 updated to show error message only as UPE100 firmware no longer goes into fatal operation
    #DMS11272018 uncomment lines marked #DMS11272018 to resort to previous version
    def ProcessingError_EventHandler(self,xml_msg):
        self.LastEventmessage=self.UPE100_GetEventText(xml_msg)
        #DMS11272018 UpdateDisplay([self.LastEventmessage, "Rebooting Reader"])
        #DMS11272018 self.UPE100.reboot_system()
        UpdateDisplay([self.LastEventmessage, "No Sale"])
       # this routine is essentially handling a user error condition of
       # not inserting the card correctly, so signal this to the DetectCardRead member function by throwing an
       # exception that it will hanlde as an authorization error
        #DMS11272018 raise Exception ("Rebooted UPE100 Due To Processing Error")


    # define method to void the last UPE100 transaction
    def VoidCC(self):
       retval=False
       self.SaleIsApproved=False
       try:
            # execute the next authorize command and print return status
            if self.UPE100.void_transaction():
                retval=True
                self.SaleIsApproved=True
                kklog.append("VoidCC:Success!")
            else:
                kklog.append("VoidCC:Void failure")
       except Exception as e:
                kklog.append("VoidCC: Got an exception during void command continue to see if it resolves " + str(e))
                self.SetReaderErrorMsg("VoidCC: Cancel transaction failed")
                retval=True
       return retval





class MagStripe_Reader(GenericReader):
    # These constants and use of the USB libs is localized to the mag stripe usb reader interface
    # so declare them within the mag stripe reader object
    VENDOR_ID = 0x0801
    PRODUCT_ID = 0x0001
    DATA_SIZE = 337
    #if RunBBBHW():
    import usb.core
    import usb.util

    def __init__(self):
            GenericReader.__init__(self)
        # initialize the reader's USB interface
        #if RunBBBHW():
            self.device = self.usb.core.find(idVendor=self.VENDOR_ID, idProduct=self.PRODUCT_ID)


            if self.device is None:
                kklog.append("Could not find MagTek USB HID Swipe Reader.")
                #sys.exit("Could not find MagTek USB HID Swipe Reader.")
            else:
                kklog.append("Initialized USB Device")
                kklog.append( self.device )

            # make sure the hiddev kernel driver is not active

            if self.device.is_kernel_driver_active(0):
                        try:
                            self.device.detach_kernel_driver(0)
                        except self.usb.core.USBError as e:
                            kklog.append("Could not detatch kernel driver: %s" % str(e))
                            #sys.exit("Could not detatch kernel driver: %s" % str(e))




            # set configuration
            try:
                self.device.set_configuration()
                self.device.reset()
            except self.usb.core.USBError as e:
                kklog.append("Could not set configuration: %s" % str(e))
                #sys.exit("Could not set configuration: %s" % str(e))

            self.endpoint = self.device[0][(0,0)][0]
            #print ("<<<<>>>>")
            #print self.endpoint
            self.data = []
            #self.swiped = False

    # Detect a card swipe - in the case of a magcard it will be card data available from the reader device
    # via the USB port
    def DetectCardRead(self):
        # run with actual card reader HW
        #if RunBBBHW():
                # look for swipe from actual card reader
                 swiped = False
                 self.data = []

                 try:
                    self.data += self.device.read(self.endpoint.bEndpointAddress, self.endpoint.wMaxPacketSize)
                    # data was read so set swiped flag to true
                    swiped = True
                    kklog.append("got CC data")
                 except Exception as E:
                    # no data was read so just return
                    kklog.append( E)
                    pass
                 return swiped

    # process - detected card read - in the case of a magcard just read all avaialble card data
    # from the device via the USB interface
    def ProcessCardRead(self):
            # run with actual card reader HW
            #if RunBBBHW():
                    # look for swipe from actual card reader
                     while True:
                         try:
                            # see if there is more card data to read
                            self.data += self.device.read(self.endpoint.bEndpointAddress, self.endpoint.wMaxPacketSize)
                         except:
                            # no more data to read so just break out and return
                            break
                         #except usb.core.USBError as e:
                            #if e.args == (110, 'Operation timed out') and self.swiped:
                                #print("decoding data")
                                # read all available data from the CC Reader
                                # so decode it
                                #DecodeCardData(data)
                                #break # got data so break out of read loop
                         #print self.data

    # mag card is not currently supported by an actual third party
    # CC processing company so just emulate the authorization and void for now
    def AuthorizeCC(self):
        self.EmulateAuthorization()

    def VoidCC(self):
        self.EmulateVoid()

    # decode the data read from the magcard
    def DecodeCardData(datalist):
        #if RunBBBHW():
            # decode the data stread read from the card reader
            """
            pseudo code

            # create a list of 8 bit bytes and remove
            # empty bytes
            ndata = []
            for d in datalist:
                if d.tolist() != [0, 0, 0, 0, 0, 0, 0, 0]:
                    ndata.append(d.tolist())

            # parse over our bytes and create string to final return
            sdata = ''
            for n in ndata:
                # handle non shifted letters
                if n[2] in chrMap and n[0] == 0:
                    sdata += chrMap[n[2]]
                # handle shifted letters
                elif n[2] in shiftchrMap and n[0] == 2:
                    sdata += shiftchrMap[n[2]]

            Now decode sdata into the various CC fields
            and save in variables for later use in the authrization function

            """
            pass


reader=None

# create a thread class to aysnchrounously poll the CC Reader
class PollCardReader(threading.Thread):
    def __init__(self):
        global reader
        threading.Thread.__init__(self)
        # Create a reader object global to all functions.
        if RunBBBHW():
            reader = UPE100_Reader()
            #reader = MagStripe_Reader()
        else:
            #reader = Emulation_Reader()
            reader = UPE100_Reader()
        #self.infile = infile
        #self.outfile = outfile
    def run(self):

        kklog.append( "\nentering PollCardReader thread" )



        # continually check for a swipe data and if there is some
        # then decode and process it.
        while GetThreadRunFlag():

                #polling should only occur if this event is set
                #poll_for_cc_read_event
                poll_for_cc_read_event.wait()

            #if RunBBBHW():
                # This is the time between seeing if a card has been swipped
                # for UPC100 it's the time between Sale commands
                # for MAG cards it's time between direclty reading the device for data
                time.sleep(.5)
                if(reader.DetectCardRead()):
                    # stop polling for now, as polling should only take place in the
                    # idle state
                    poll_for_cc_read_event.clear()
                    #
                    # make sure the user removes the card from the reader
                    # before proceeding this is important for chip card insert type readers
                    # first give the user a few seconds to remove the card
                    time.sleep(3)
                    # now check and see if the card is removed
                    # and keep on checking until it is
                    while(reader.CardInserted()==True):
                        UpdateDisplay(["PLEASE REMOVE CARD"])
                        time.sleep(1)
                    #
                    # update the fsm with the card swipe event
                    # this is done now before all the data is read
                    # for better response to the user
                    # otherwise for mag cards it will be a number of seconds before
                    # all the data is read and there will be that
                    # much delay going into the
                    # next (authorize) fsm state
                    fsm_event_queue.append(e_cardswipe)
                    # now process the card read
                    reader.ProcessCardRead()
                    # signal authorization function that all card data has been read
                    # and it can proceed with the authorization processing
                    proceed_with_authorization_event.set()
                else:
                    # did not detect a current a card read so start transaction logging for the
                    # new card read attempt
                    kklog.start_transaction()


        kklog.append( "Leaving PollCardReader thread" )


def ExecuteAuthorizeCCState():

    # perfrom the authorization via the actual method defined by the reader object
            # wait for the CC swipe to be detected before authorizing
            if proceed_with_authorization_event.wait(CARD_WAIT_TIME):
                proceed_with_authorization_event.clear()

                kklog.append("ExecuteAuthorizeCCState:authorizing Card")
                reader.AuthorizeCC()
                if(reader.SaleIsApproved==True):
                    fsm_event_queue.append(e_authorized)
                else:
                    err_reason = reader.GetReaderErrorMsg()
                    fsm_error_queue.append(err_reason) # reason to be generated above
                    fsm_event_queue.append(e_authorization_err)

            else:
                fsm_error_queue.append("Could not read card data") # reason to be generated above
                fsm_event_queue.append(e_authorization_err)


def ExecuteCancelCCState():

    # after doing the cancellation (which is a form of authorization)
    # return any error by sending a error message and
    # sending an authorization error event to the fsm
    if(reader.VoidCC()==False):
        fsm_error_queue.append(err_reason) #  reason to be generated above
        fsm_event_queue.append(e_authorization_err)

def ExecuteAudibleAlert():
    res = reader.AudibleAlert()
    return(res)

def RebootReader(wait_time=30):
    res = reader.RebootReader(wait_time)
    return(res)

def UpdateFirmware(wait_time=120):
    res = reader.UpdateFirmware(wait_time)


