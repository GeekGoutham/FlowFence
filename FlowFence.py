from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import *
from pox.lib.util import dpidToStr
from pox.lib.addresses import EthAddr, IPAddr
from collections import namedtuple
from pox.topology.topology import Switch, Entity
from pox.lib.revent import EventMixin
import pox.lib.packet as pkt
import os
import  sys, socket, json, subprocess
import thread 
from threading import Thread
from collections import deque

import time
import math
#######################################

log = core.getLogger()
controllerIp = '10.1.4.1' # The host is receiving by eth3
#controllerIp = '127.0.0.1' # The host is receiving by eth3

############################here is the socket server ####
class server_socket(Thread):
	
	def __init__(self, connections):
		Thread.__init__(self)
		global received
		self.sock = None
		#self.status =-1			
		self.connections = connections						#dpdi of the switch

	def run(self):
		self.sock = socket.socket()         				# Create a socket object
		host = controllerIp									
		port = 12345               							# Reserve a port for own communication btwn switches and controller
		log.info("Binding to listen for switch messages")
		self.sock.bind((host, port))        				# Bind to the port
		self.sock.listen(5)                	 				# Now wait for client connection.

		while True:												
			try:
			
				client, addr = self.sock.accept()				# Establish connection with client
				data = client.recv(1024)						# Get data from the client 
				print 'Message from', addr 						# Print a message confirming 
				data_treatment = handle_message(data,self.connections, addr)	# Call the thread to work with the data received
				data_treatment.setDaemon(True)					# Set the thread as a demond
				data_treatment.start()							# Start the thread

			except KeyboardInterrupt:
				print "\nCtrl+C was hitten, stopping server"
				client.close()
				break
		
#########################
class handle_message(Thread):

	def __init__(self,received,connections, addr):
		Thread.__init__(self)
		self.received = received
		self.myconnections = connections
		self.srcAddress = addr[0]
		self.alfa=1
		print self.myconnections

	def run(self):
		
		print 'message from ' + str(self.srcAddress)
		#print 'Connections '
		#print self.myconnections
		#print self.received + '\n'

		try:
			message = eval(json.loads(self.received))
			print "Message received " + str(message)
		except:
			print "An error ocurred processing the incoming message"

		print "Type of message " + str(message['Notification'])
	
		if message['Notification'] == 'Congestion':
			self.handleCongestionNotification(message)
		elif message['Notification'] == 'Uncongestion':
			self.handleUncongestionNotification(message)

		#aux_dpid=message[0]['src']
		#nocoma=aux_dpid[:len(aux_dpid)-1]
		#print 'No coma dpid: ' + nocoma
		#corrected=nocoma[len(nocoma)-13:]
		#corrected=corrected[:len(corrected)-1]
		#print 'Received dpid: ' + aux_dpid
        #print 'Corrected dpid: ' + corrected
		#linkId = message[0]['linkId']

		#print 'linkId' + str(linkId)
		
		#Let's try to find a match

		#todo: For now, we're doing this manually. We really should check how many pairs src, linkId are and mod those flows for the respective queues
		#senders=10
		#addresses=['10.1.1.1', '10.1.1.2', '10.1.1.3', '10.1.1.4', '10.1.1.5', '10.1.1.6', '10.1.1.7', '10.1.1.9', '10.1.1.10', '10.1.1.11']
		#addresses=['10.1.1.1', '10.1.1.3']
		#addresses=['10.1.1.1', '10.1.1.2', '10.1.1.3', '10.1.1.4']
		#addresses=['10.1.1.1', '10.1.1.2', '10.1.1.3', '10.1.1.4', '10.1.1.5', '10.1.1.6', '10.1.1.7']		

		#for i in range(senders):
			
		#my_match = of.ofp_match(dl_type = 0x800,
		#nw_src=IPAddr(addresses[i]),		#toDo: Get Flowlist going to destination
		#nw_dst=linkId,
		#in_port=65534)

		#msg = of.ofp_flow_mod()
		#msg.match = my_match
		#msg.priority=65535		

		#msg.actions.append(of.ofp_action_enqueue(port=1, queue_id=(i+1)))
	
		#for connection in self.myconnections:
		#dpid=connection.dpid
		#dpidStr=dpidToStr(dpid)
		#dpidStr=dpidStr.replace("-", "")
		#print 'Real dpidStr: ' + dpidStr
		#print 'rec_dpid: ' + corrected 
		#corrected=dpidStr[len(dpidStr)-12:]
		#if corrected == dpidStr:
		#connection.send(msg)
		#print 'Sent to: ' + str(connection)
		#print 'Well...done'	

############################

	def handleCongestionNotification(self, notificationMessage):
		# Algorithm: Classify good and bad flows, assign bandwidth fo good flows, assign band fo bad flows, assign remaining band
		# Bad flows bw: assignedBw(j,i)=avaliableBw/badFlows - (1 -exp( - (rates(i)-capacityOverN) ) )*alfas(j)*rates(i);

		flowBwList=[]
		flowBwDict=dict.fromkeys(['srcIp','dstIp','goodBehaved','bandwidth'])
		badFlows=0
		bwForBadFlows=0

		remainingBw = notificationMessage['Interface']['capacity']

		# Good Flows
		for i in range(len(notificationMessage['Flowlist'])):
			flowBwDict['srcIp'] = notificationMessage['Flowlist'][i]['srcIp']
			flowBwDict['dstIp'] = notificationMessage['Flowlist'][i]['dstIp']
			flowBwDict['goodBehaved'] = self.classifyFlows(notificationMessage['Interface']['capacity'], notificationMessage['Flowlist'][i]['arrivalRate'],len(notificationMessage['Flowlist']))

			if flowBwDict['goodBehaved'] == True:
				flowBwDict['bw']= notificationMessage['Flowlist'][i]['arrivalRate']
				remainingBw = remainingBw - notificationMessage['Flowlist'][i]['arrivalRate']
			else:
				badFlows=badFlows+1

			flowBwList.append(flowBwDict)

		bwForBadFlows=remainingBw

		# Bad Flows
		for i in range(len(notificationMessage['Flowlist'])):
			if flowBwDict['goodBehaved'] == False:
				flowBwList[i]['bw']= assignBwToBadBehaved(bwForBadFlows, badFlows, notificationMessage['Interface']['capacity'], len(notificationMessage['Flowlist']), notificationMessage['Flowlist'][i]['arrivalRate'], self.alfa)
				# Here we should check witch switches also handle the bad behaved flow to apply the same control, in the simplest topology (Dumb-bell), it is not neccesary
				remainingBw = remainingBw - flowBwList[i]['bw']

		# Give remmaining bw between good flows
		for i in range(len(notificationMessage['Flowlist'])):
			if flowBwDict['goodBehaved'] == True:
				flowBwList[i]['bw']= remainingBw/(len(notificationMessage['Flowlist']) - badFlows)
		
		print "Calculated Bandwidth: " + str(flowBwList)
		
	#In further versions, other classification methods could be used
	def classifyFlows(self, capacity, estimatedBw, numFlows):
		if (estimatedBw>capacity/numFlows):
			return False
		else:
			return True

	def assignBwToBadBehaved(avaliableBw, numBadFlows, capacity, numTotalFlows, flowRate, alfa):
		#assignedBw(j,i)=avaliableBw/badFlows - (1 -exp( - (rates(i)-capacityOverN) ) )*alfas(j)*rates(i);		
		return avaliableBw/numBadFlows - (1 - math.exp(-(flowRate-(capacity/numTotalFlows))))*alfa*flowRate


class connect_test(EventMixin):	
  # Waits for OpenFlow switches to connect and makes them learning switches.
	#Global variables of connect_test subclass
	#global received
	def __init__(self):
		self.listenTo(core.openflow)
		log.debug("Received connection from switch")
		self.myconnections=[]		# a list of the connections
		socket_server=server_socket(self.myconnections)	# send it to the socket with the connection 
		socket_server.setDaemon(True)		# establish the thread as a deamond, this will make to close the thread with the main program
		socket_server.start()				# starting the thread

	def _handle_ConnectionUp (self, event):
		print event.dpid #it prints the switch connection information, on the screen
		self.myconnections.append(event.connection)	# will pass as a reference to above

#######################################


def launch ():
	#core.openflow.addListenerByName("FlowStatsReceived", listarFluxosIp)
	core.registerNew(connect_test)

