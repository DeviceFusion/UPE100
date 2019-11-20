#-------------------------------------------------------------------------------
# coding: utf-8

#-------------------------------------------------------------------------------
# Name:        UPE100 test code
# Purpose:     sample code to test the high level programmng interface to the
#              UIC UPE-100 CC Payment Device (UPE100.py library).
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
#-------------------------------------------------------------------------------
import time
#import the UPE100 CC reader Object
from UPE100 import upe100
from UPE100 import TXN_ACCEPTED





# generic event handler function to demo how UPE100 application event callbacks work
def application_EventHandler(xml_msg):
        # print this event's text
        from xml.etree import ElementTree as ET
        try:
            formatted_xml = "<?xml version='1.0' encoding='UTF-8'?>" + \
                        "<!DOCTYPE xgdresponse SYSTEM 'xgdresponse.dtd'>" + \
                        "<xgdresponse version='1.0'>" + \
                        xml_msg + "</xgdresponse>"
            print(">>>>>>>>>>Demo:application_EventHandler:" + ET.fromstring(formatted_xml.strip()).find('Event/Type/ReqDispMesg/MesgStr').text)
        except:
            print(">>>>>>>>>>Demo:application_EventHandler: error extracting message string")


def upe100_function_demo():

    global runtest

    i=1
    # Reuse the same instance of the upe_cc in each loop
    ccr = upe100(uic_ip_address = '192.168.0.250',uic_authorize_timeout=30.0, uic_in_progress_timeout=45.0)

    # setup the UPE100 event call backs just for demo purposes
    # Note: this demo uses the same callback function for all events
    # but the UPE100 class supports per event callbacks so a different
    # callback function can be set for each event if desired.
    #
    #"24":PLEASE SWIPE OR INSERT CARD
    ccr.set_application_event_callbackfunction("24",application_EventHandler)
    #"14":PLEASE WAIT...
    ccr.set_application_event_callbackfunction("14",application_EventHandler)
    #"16":PLEASE REMOVE CARD
    ccr.set_application_event_callbackfunction("16",application_EventHandler)
    #"27":AUTHORIZING. PLEASE WAIT...
    ccr.set_application_event_callbackfunction("27",application_EventHandler)
    #"28":"PLEASE TRY ANOTHER CARD"
    ccr.set_application_event_callbackfunction("28",application_EventHandler)
    # "18":"PLEASE USE MAGSTRIPE CARD"
    ccr.set_application_event_callbackfunction("18",application_EventHandler)
    #"36":TRANSACTION DATA UPDATING...
    ccr.set_application_event_callbackfunction("36",application_EventHandler)
    #"34":PROCESSING OK
    ccr.set_application_event_callbackfunction("34",application_EventHandler)

    # run sale cycles until the user says to quit.
    while (True):
        print(">>>>>>>>>>Sale Cycle:" + str(i))
        try:
            # execute the next authorize command and print return status
            if ccr.authorize("1.29"):
                # a card was swiped and authorized so process accordingly
                if(ccr.txn_result == TXN_ACCEPTED):
                    print(">>>>>>>>>>Demo:Card Approved")
                    # demo for void command; uncomment the lines below
                    #time.sleep(5)
                    #print(">>>>>>>>>>Demo:Voiding Transaction")
                    #ccr.void_transaction()
                else:
                    print(">>>>>>>>>>Demo:Card Declined")

            else:
                print(">>>>>>>>>>Demo:Sale timeout - no card presented")
        except Exception as e:
            # catch any exceptions that occur at any level in the auhtorize code by displaying it
            print("Test: Got an exception " + str(e))
            #break

        # demo to check if card is still inserted
        # don't start next sale cycle until the card has been removed
        while(ccr.check_cc_inserted()==True):
            print(">>>>>>>>>>Demo:PLEASE REMOVE CARD")
            time.sleep(3)

        # audible signal demo : signal to start next loop
        ccr.audible_alert("2","250","250")
        # see if the user wants another sale
        if raw_input("\nDemo:Start another sale? (y/n)").lower().startswith('n'):
            break
        i += 1

    # exited while loop so gracefully delete the upe ccr object
    del(ccr)




def main():
    # run the demo
    upe100_function_demo()

if __name__ == '__main__':
    main()