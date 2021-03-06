# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
An OpenFlow 1.0 L2 learning switch implementation.
"""

import logging
import struct

from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_0, ether
from ryu.lib.mac import haddr_to_bin
from ryu.lib.mac import haddr_to_str
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import arp, ipv4
from ryu.lib.packet import lldp
from ryu.topology.switches import LLDPPacket



class SimpleSwitch(app_manager.RyuApp):
	OFP_VERSIONS = [ofproto_v1_0.OFP_VERSION]
	hostCounter = 0 #Global variable for traffic counter on specified host
	def __init__(self, *args, **kwargs):
		super(SimpleSwitch, self).__init__(*args, **kwargs)
		self.mac_to_port = {}
	def add_flow(self, datapath, in_port, dst, actions):
		ofproto = datapath.ofproto
		match = datapath.ofproto_parser.OFPMatch(
			in_port=in_port, dl_dst=haddr_to_bin(dst))

		mod = datapath.ofproto_parser.OFPFlowMod(
			datapath=datapath, match=match, cookie=0,
			command=ofproto.OFPFC_ADD, idle_timeout=0, hard_timeout=0,
			priority=ofproto.OFP_DEFAULT_PRIORITY,
			flags=ofproto.OFPFF_SEND_FLOW_REM, actions=actions)
		datapath.send_msg(mod)

	@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
	def _packet_in_handler(self, ev):
		msg = ev.msg
		datapath = msg.datapath
		ofproto = datapath.ofproto
		pkt = packet.Packet(msg.data)
		eth = pkt.get_protocol(ethernet.ethernet)
		arp_packet = pkt.get_protocol(arp.arp)
		ipv4_packet = pkt.get_protocol(ipv4.ipv4)
		lldp_packet = pkt.get_protocol(lldp.lldp)
		
		#block for debugging, prints packet type.
		if arp_packet:
			pack = arp_packet
			self.logger.info("The packet is: %s", pack)
		elif ipv4_packet:
			pack = ipv4_packet
			self.logger.info("The packet is: %s", pack)	
		elif lldp_packet:
			pack = lldp_packet
			self.logger.info("The packet is: %s", pack)
		else:
			pack = eth
			self.logger.info("The packet is: %s", pack)
			
        
        #Setup source and destination addresses
		dst = eth.dst
		src = eth.src

		dpid = datapath.id
		self.mac_to_port.setdefault(dpid, {})
		
				
		
		if(dst == "00:00:00:00:00:01" or src == "00:00:00:00:00:01"): #Checks whether the packet originated from, or is going to host 1
			self.hostCounter +=1
			self.logger.info("%s Packets have been sent to or from host 1", self.hostCounter)			
			self.logger.info("Packet logic is now executing")
        # learn a mac address to avoid FLOOD next time.
		self.mac_to_port[dpid][src] = msg.in_port
		if dst in self.mac_to_port[dpid]:
			out_port = self.mac_to_port[dpid][dst]
		else:
			out_port = ofproto.OFPP_FLOOD

		actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
	
		# install a flow to avoid packet_in next time
		if out_port != ofproto.OFPP_FLOOD and not(dst == "00:00:00:00:00:01" or src == "00:00:00:00:00:01"):
			self.add_flow(datapath, msg.in_port, dst, actions)
				
			
			
		out = datapath.ofproto_parser.OFPPacketOut(
			datapath=datapath, buffer_id=msg.buffer_id, in_port=msg.in_port,
			actions=actions)
		datapath.send_msg(out)

			
			
	@set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
	def _port_status_handler(self, ev):
		msg = ev.msg
		reason = msg.reason
		port_no = msg.desc.port_no

		ofproto = msg.datapath.ofproto
		if reason == ofproto.OFPPR_ADD:
			self.logger.info("port added %s", port_no)
		elif reason == ofproto.OFPPR_DELETE:
			self.logger.info("port deleted %s", port_no)
		elif reason == ofproto.OFPPR_MODIFY:
			self.logger.info("port modified %s", port_no)
		else:
			self.logger.info("Illegal port state %s %s", port_no, reason)#Modified Spelling Mistakes

	#Set of rules to block IP traffic between h2 and h3		
	def block_traffic_by_default(self, dp):
		ofproto = dp.ofproto
		parser = dp.ofproto_parser
		match = parser.OFPMatch(dl_type=ether.ETH_TYPE_IP, dl_src=haddr_to_bin("00:00:00:00:00:02"), dl_dst=haddr_to_bin("00:00:00:00:00:03"))
		mod = parser.OFPFlowMod(datapath = dp, match = match, cookie=0, command=ofproto.OFPFC_ADD, hard_timeout = 0,  priority=ofproto.OFP_DEFAULT_PRIORITY, actions = [])
		dp.send_msg(mod)
		secondmatch = parser.OFPMatch(dl_type=ether.ETH_TYPE_IP, dl_dst=haddr_to_bin("00:00:00:00:00:03"), dl_src=haddr_to_bin("00:00:00:00:00:02"))
		mod = parser.OFPFlowMod(datapath = dp, match = secondmatch, cookie=0, command=ofproto.OFPFC_ADD, hard_timeout = 0, priority=ofproto.OFP_DEFAULT_PRIORITY, actions = [])
		dp.send_msg(mod)
		
	#event handler to start traffic block on startup	
	@set_ev_cls(ofp_event.EventOFPStateChange, MAIN_DISPATCHER)
	def on_startup_event(self, ev):
		datapath = ev.datapath
		self.logger.info("Started with event MAIN_DISPATCHER")
		self.block_traffic_by_default(datapath)
	
	
		
		
	

		
		

		

		
		
		
		
	
	
	
	
	
