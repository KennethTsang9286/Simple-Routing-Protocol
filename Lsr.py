#python3

UPDATE_INTERVAL = 1.0
ROUTE_UPDATE_INTERVAL = 2.0
HEARTBEAT_INTERVAL = 1.0
DEAD_HEARTBEAT_INTERVAL = 3.0
UDP_IP_ADDRESS = "127.0.0.1"

import socket
import time
import threading
import sys
import json
import logging
from collections import defaultdict

#https://www.tutorialspoint.com/python/python_multithreading.htm
#https://stackoverflow.com/questions/27893804/udp-client-server-socket-in-python
#https://www.pythonforbeginners.com/system/python-sys-argv
#https://tutorialedge.net/python/udp-client-server-python/
#https://stackoverflow.com/questions/15190362/sending-a-dictionary-using-sockets-in-python

def repeat_call(start_time, interval, f):
	while True:
		f()
		time.sleep(float(interval) - ((time.time() - start_time)%float(interval)))

def propagation(name, entity, msg):
	for neighbour in [x for x in entity.distances[entity.router_id] if not x == msg['host']]:
		server_address = (UDP_IP_ADDRESS, entity.ports[neighbour])
		logging.debug(f"{name}ing: propagation from {entity.router_id} to {neighbour}")
		try:
			sent = entity.socket.sendto(json.dumps(msg).encode('utf-8'), server_address)
			logging.debug(f"{name}ed: propagation from {entity.router_id} to {neighbour}")
		except:
			logging.warning(f"{name}: propagation error: from {entity.router_id} to {neighbour}")
			pass


class Heartbeat:
	def __init__(self, lsr):
		self.heartbeat = {}
		self.lsr = lsr

	def update_heartbeat(self, _id):
		self.heartbeat[_id] = time.time()
	
	#only check neigbour
	def check_heartbeat(self):
		logging.info("check_heartbeat")
		cur_time = time.time()
		for _id in (x for x in self.heartbeat if self.is_alive(x)):
			if cur_time - self.heartbeat[_id] > DEAD_HEARTBEAT_INTERVAL:
				logging.info(f"FOUND DEAD: {_id}")
				self.load_dead_news(_id)
	
	def is_alive(self, _id):
		return self.lsr.distances[_id]

	def load_dead_news(self, _id):
		logging.debug("load_dead_news")
		self.lsr.distances[_id] = {}
		for node in self.lsr.distances:
			for node_neigbor in self.lsr.distances[node]:
				if node_neigbor == _id:
					self.lsr.distances[node][node_neigbor] = float('inf')

#/PART 2

class Calculation(threading.Thread):
	def __init__(self, threadID, lsr):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.lsr = lsr
	
	def init_dict(self):
		self.shortest_distances = {}
		self.shortest_paths = defaultdict(lambda: "")
		self.visited = defaultdict(lambda: False)
		for node in self.lsr.distances:
			self.shortest_distances[node] = 0.0 if self.lsr.router_id == node else float('inf')
			self.visited[node] = False
		

	def run(self):
		logging.info(f"{self.lsr.router_id}: start calculation")
		self.start_calculation()

	def start_calculation(self):
		repeat_call(time.time(), ROUTE_UPDATE_INTERVAL, self.calculation)

	def calculation(self):
		logging.debug("calculation")
		self.init_dict()
		self._calculation()
		self.print_cal()

	def _calculation(self):
		myself = self.lsr.router_id
		self.shortest_distances[myself] = 0.0
		self.shortest_paths[myself] = myself
		self._calculation_recur(myself)

	def _calculation_recur(self, node):
		myself = node
		distances = self.lsr.distances
		neighbours = [x for x in distances[myself] if (x in distances) and (not self.visited[x]) and (distances[x])]
		if len(neighbours) == 0:
			return 0

		for neighbour in neighbours:
			trial_distance = self.shortest_distances[myself] + distances[myself][neighbour]
			if trial_distance < self.shortest_distances[neighbour]:
				self.shortest_distances[neighbour] = trial_distance
				self.shortest_paths[neighbour] = self.shortest_paths[myself] + neighbour
		self.visited[myself] = True
		next_node = self._find_min()
		if next_node:
			self._calculation_recur(next_node)

	def _find_min(self):
		output_distance = float('inf')
		output_node = None
		for node in list(self.shortest_distances):
			if node != self.lsr.router_id and not self.visited[node] and output_distance > self.shortest_distances[node]:
				output_node = node
				output_distance = self.shortest_distances[output_node]
		if output_distance == float('inf'):
			return None
		else:
			return output_node
			
	def print_cal(self):
		print(f"I am Router {self.lsr.router_id}")
		for _id in sorted([n for n in self.lsr.distances if n != self.lsr.router_id and self.shortest_distances[n] != float('inf')]):
			sd = self.shortest_distances[_id]
			sp = self.shortest_paths[_id]
			print(f"Least cost path to router {_id}:{sp} and the cost: {sd}")

class Listen(threading.Thread):
	def __init__(self, threadID, lsr):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.lsr = lsr

	def run(self):
		logging.info(f"{self.lsr.router_id}: start running")
		self.start_server()		

	def start_server(self):
		server_address = (UDP_IP_ADDRESS, self.lsr.ports[self.lsr.router_id])
		self.lsr.socket.bind(server_address)
		while True:
			data, addr = self.lsr.socket.recvfrom(1024)
			data = json.loads(data)
			if self.is_retransmit(data):
				self.retransmit(data)
				self.lsr.heartbeat.update_heartbeat(data['host'])
			self.load_package(data)
			
	
	# {
	# 	'host': self.router_id,
	# 	'distances': self.distances[self.router_id]
	# }

	def is_retransmit(self, data):
		return ( 
			(not data['host'] in self.lsr.heartbeat.heartbeat) or 
			(data['time'] > self.lsr.heartbeat.heartbeat[data['host']] + UPDATE_INTERVAL )
		)

	def load_package(self, data):
		logging.debug('load_package')
		host = data['host']
		distances = self.lsr.distances
		distances[host] = data['distances']
		for node in distances:
			for local_neighbor in distances[node]:
				if local_neighbor == host:
					distances[node][local_neighbor] = data['distances'][node]


	def retransmit(self, data):
		logging.debug('retransmit')
		propagation("retransmit", self.lsr, data)
			
class Sending(threading.Thread):
	def __init__(self, threadID, lsr):
		threading.Thread.__init__(self)
		self.threadID = threadID
		self.lsr = lsr
		self.start_time = time.time()

	#for testing
	def print_health_check(self):
		logging.debug([ (x, f"dead: {time.time() - self.lsr.heartbeat.heartbeat[x] > DEAD_HEARTBEAT_INTERVAL}")  for x in self.lsr.heartbeat.heartbeat])
		logging.debug(f"{self.lsr.router_id}: {list(self.lsr.distances)}")

	def run(self):
		repeat_call(self.start_time, UPDATE_INTERVAL, self._run)

	def _run(self):
		self.print_health_check()
		self.send_msgs()
		self.lsr.heartbeat.check_heartbeat()

	def send_msgs(self):
		logging.debug("send_msgs")
		propagation('send_msgs', self.lsr, self.struct_content())

	def struct_content(self):
		return {
			'host': self.lsr.router_id,
			'distances': self.lsr.distances[self.lsr.router_id],
			'time': time.time()
		}

class Lsr():
	def __init__(self, router_id, router_port, config_path):
		self.router_id = router_id
		self.ports = {}
		self.ports[router_id] = int(router_port)
		self.distances = {}
		self.distances[router_id] = {}
		self.heartbeat = {}
		self.read_config(config_path)
		self.init_neigbour_heartbeat()
		self.print_info()
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		self.heartbeat = Heartbeat(self)
		self.listen = Listen(1, self)
		self.listen.start()
		self.sending = Sending(2, self)
		self.sending.start()
		self.calculation = Calculation(3, self)
		self.calculation.start()

	def init_neigbour_heartbeat(self):
		cur_time = time.time()
		for neighbour in self.distances[self.router_id]:
			self.heartbeat[neighbour] = cur_time

	def read_config(self, config_path):
		with open(config_path, "r") as f:
			f = list(f)
			for line in f[1:]:
				if not line.isspace():
					node_info = line.split()
					self.ports[node_info[0]] = int(node_info[2])
					self.distances[self.router_id][node_info[0]] = float(node_info[1])

	def print_info(self):
		logging.debug("My router_id: ", self.router_id)
		logging.debug("ports: \n", self.ports)
		logging.debug("distances: \n", self.distances)


if __name__ == "__main__":
	level = sys.argv[4][6:] if len(sys.argv) > 4 else 'WARNING'
	logging.getLogger().setLevel(logging.__dict__[level])
	lsr = Lsr(*sys.argv[1:4])
	
