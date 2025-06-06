#!/usr/bin/env python3
"""
WebSocket桥接服务器
连接ROS2系统和前端WebSocket客户端
"""

import asyncio
import websockets
import json
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
import threading
from geometry_msgs.msg import PoseStamped, Twist
from visualization_msgs.msg import MarkerArray
from auto_msgs.msg import GridMap, PlanningPath, PlanningRequest
from std_msgs.msg import String
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ROS2WebSocketBridge(Node):
    def __init__(self, loop):
        super().__init__('websocket_bridge')
        self.loop = loop  # 存储主线程的事件循环
        
        # WebSocket客户端列表
        self.websocket_clients = set()
        
        # ROS2订阅者
        self.vehicle_state_sub = self.create_subscription(
            PoseStamped, '/vehicle_state', self.vehicle_state_callback, 10
        )
        self.objects_sub = self.create_subscription(
            MarkerArray, '/detected_objects', self.objects_callback, 10
        )
        self.gridmap_sub = self.create_subscription(
            GridMap, '/grid_map', self.gridmap_callback, 10
        )
        self.path_sub = self.create_subscription(
            PlanningPath, '/planning_path', self.path_callback, 10
        )
        
        # JSON格式的订阅者
        self.gridmap_json_sub = self.create_subscription(
            String, '/grid_map_json', self.gridmap_json_callback, 10
        )
        self.planning_request_json_sub = self.create_subscription(
            String, '/planning_request_json', self.planning_request_json_callback, 10
        )
        
        # ROS2发布者
        self.planning_request_pub = self.create_publisher(
            PlanningRequest, '/planning_request', 10
        )
        self.control_cmd_pub = self.create_publisher(
            Twist, '/control_cmd', 10
        )
        
        logger.info("ROS2 WebSocket Bridge initialized")

    def add_websocket_client(self, websocket):
        """添加WebSocket客户端"""
        self.websocket_clients.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")

    def remove_websocket_client(self, websocket):
        """移除WebSocket客户端"""
        self.websocket_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}")

    async def broadcast_to_websockets(self, message):
        """向所有WebSocket客户端广播消息"""
        if self.websocket_clients:
            clients_copy = self.websocket_clients.copy()
            disconnected_clients = set()
            
            for client in clients_copy:
                try:
                    await client.send(json.dumps(message))
                except websockets.exceptions.ConnectionClosed:
                    disconnected_clients.add(client)
                except Exception as e:
                    logger.error(f"Error sending message to client: {e}")
                    disconnected_clients.add(client)
            
            for client in disconnected_clients:
                self.remove_websocket_client(client)

    def vehicle_state_callback(self, msg):
        """车辆状态回调"""
        message = {
            'topic': '/vehicle_state',
            'msg': {
                'pose': {
                    'position': {
                        'x': msg.pose.position.x,
                        'y': msg.pose.position.y,
                        'z': msg.pose.position.z
                    },
                    'orientation': {
                        'x': msg.pose.orientation.x,
                        'y': msg.pose.orientation.y,
                        'z': msg.pose.orientation.z,
                        'w': msg.pose.orientation.w
                    }
                }
            }
        }
        # 安全调度协程到主线程事件循环
        asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)

    def objects_callback(self, msg):
        """检测对象回调"""
        markers = []
        for marker in msg.markers:
            markers.append({
                'id': marker.id,
                'ns': marker.ns,
                'pose': {
                    'position': {
                        'x': marker.pose.position.x,
                        'y': marker.pose.position.y,
                        'z': marker.pose.position.z
                    },
                    'orientation': {
                        'x': marker.pose.orientation.x,
                        'y': marker.pose.orientation.y,
                        'z': marker.pose.orientation.z,
                        'w': marker.pose.orientation.w
                    }
                },
                'scale': {
                    'x': marker.scale.x,
                    'y': marker.scale.y,
                    'z': marker.scale.z
                },
                'color': {
                    'r': marker.color.r,
                    'g': marker.color.g,
                    'b': marker.color.b,
                    'a': marker.color.a
                }
            })
        
        message = {
            'topic': '/detected_objects',
            'msg': {
                'markers': markers
            }
        }
        asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)

    def gridmap_callback(self, msg):
        """网格地图回调"""
        message = {
            'topic': '/grid_map',
            'msg': {
                'width': msg.width,
                'height': msg.height,
                'resolution': msg.resolution,
                'origin': {
                    'position': {
                        'x': msg.origin.position.x,
                        'y': msg.origin.position.y,
                        'z': msg.origin.position.z
                    }
                },
                'data': list(msg.data)
            }
        }
        asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)

    def path_callback(self, msg):
        """规划路径回调"""
        points = []
        for point in msg.points:
            points.append({
                'pose': {
                    'pose': {
                        'position': {
                            'x': point.pose.position.x,
                            'y': point.pose.position.y,
                            'z': point.pose.position.z
                        },
                        'orientation': {
                            'x': point.pose.orientation.x,
                            'y': point.pose.orientation.y,
                            'z': point.pose.orientation.z,
                            'w': point.pose.orientation.w
                        }
                    }
                },
                'velocity': point.velocity,
                'curvature': point.curvature
            })
        
        message = {
            'topic': '/planning_path',
            'msg': {
                'header': {
                    'frame_id': msg.header.frame_id,
                    'stamp': {
                        'sec': msg.header.stamp.sec,
                        'nanosec': msg.header.stamp.nanosec
                    }
                },
                'points': points,
                'planner_type': msg.planner_type,
                'total_distance': msg.total_distance,
                'planning_time': msg.planning_time
            }
        }
        asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)
        
    def gridmap_json_callback(self, msg):
        """JSON格式网格地图回调 - 只转发不解析"""
        try:
            # 直接转发原始JSON数据，不进行解析
            message = {
                'topic': '/grid_map_json',
                'json': True,
                'raw_data': msg.data  # 直接转发原始JSON字符串
            }
            
            # 直接转发到WebSocket客户端
            asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)
            logger.debug("JSON地图数据直接转发至WebSocket")
            
        except Exception as e:
            logger.error(f"转发JSON地图数据时出错: {e}")
    
    def planning_request_json_callback(self, msg):
        """JSON格式规划请求回调 - 只转发不解析"""
        try:
            # 直接转发原始JSON数据，不进行解析
            message = {
                'topic': '/planning_request_json',
                'json': True,
                'raw_data': msg.data  # 直接转发原始JSON字符串
            }
            
            # 直接转发到WebSocket客户端
            asyncio.run_coroutine_threadsafe(self.broadcast_to_websockets(message), self.loop)
            logger.debug("JSON规划请求数据直接转发至WebSocket")
            
        except Exception as e:
            logger.error(f"转发JSON规划请求数据时出错: {e}")

    def handle_websocket_message(self, message_data):
        """处理来自WebSocket的消息"""
        try:
            message = json.loads(message_data)
            op = message.get('op')
            topic = message.get('topic')
            msg_data = message.get('msg', {})

            if op == 'publish':
                if topic == '/planning_request':
                    planning_msg = PlanningRequest()
                    planning_msg.header.frame_id = msg_data.get('header', {}).get('frame_id', 'map')
                    
                    start_data = msg_data.get('start', {}).get('pose', {})
                    start_pos = start_data.get('position', {})
                    start_ori = start_data.get('orientation', {})
                    
                    planning_msg.start.pose.position.x = float(start_pos.get('x', 0))
                    planning_msg.start.pose.position.y = float(start_pos.get('y', 0))
                    planning_msg.start.pose.position.z = float(start_pos.get('z', 0))
                    planning_msg.start.pose.orientation.x = float(start_ori.get('x', 0))
                    planning_msg.start.pose.orientation.y = float(start_ori.get('y', 0))
                    planning_msg.start.pose.orientation.z = float(start_ori.get('z', 0))
                    planning_msg.start.pose.orientation.w = float(start_ori.get('w', 1))
                    
                    goal_data = msg_data.get('goal', {}).get('pose', {})
                    goal_pos = goal_data.get('position', {})
                    goal_ori = goal_data.get('orientation', {})
                    
                    planning_msg.goal.pose.position.x = float(goal_pos.get('x', 0))
                    planning_msg.goal.pose.position.y = float(goal_pos.get('y', 0))
                    planning_msg.goal.pose.position.z = float(goal_pos.get('z', 0))
                    planning_msg.goal.pose.orientation.x = float(goal_ori.get('x', 0))
                    planning_msg.goal.pose.orientation.y = float(goal_ori.get('y', 0))
                    planning_msg.goal.pose.orientation.z = float(goal_ori.get('z', 0))
                    planning_msg.goal.pose.orientation.w = float(goal_ori.get('w', 1))
                    
                    planning_msg.planner_type = msg_data.get('planner_type', 'hybrid_astar')
                    planning_msg.consider_kinematic = msg_data.get('consider_kinematic', True)
                    
                    self.planning_request_pub.publish(planning_msg)
                    logger.info("Published planning request")

                elif topic == '/control_cmd':
                    control_msg = Twist()
                    control_msg.linear.x = float(msg_data.get('linear', {}).get('x', 0))
                    control_msg.linear.y = float(msg_data.get('linear', {}).get('y', 0))
                    control_msg.linear.z = float(msg_data.get('linear', {}).get('z', 0))
                    control_msg.angular.x = float(msg_data.get('angular', {}).get('x', 0))
                    control_msg.angular.y = float(msg_data.get('angular', {}).get('y', 0))
                    control_msg.angular.z = float(msg_data.get('angular', {}).get('z', 0))
                    
                    self.control_cmd_pub.publish(control_msg)
                    logger.info("Published control command")

        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")

# 全局桥接节点实例
bridge_node = None

async def handle_websocket_client(websocket, path=None):
    """处理WebSocket客户端连接"""
    global bridge_node
    
    if bridge_node is None:
        logger.error("Bridge node not initialized")
        return
    
    bridge_node.add_websocket_client(websocket)
    
    try:
        async for message in websocket:
            bridge_node.handle_websocket_message(message)
    except websockets.exceptions.ConnectionClosed:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        bridge_node.remove_websocket_client(websocket)

def run_ros2_node(loop):
    """在单独线程中运行ROS2节点"""
    global bridge_node
    
    rclpy.init()
    bridge_node = ROS2WebSocketBridge(loop)  # 传递事件循环
    
    executor = MultiThreadedExecutor()
    executor.add_node(bridge_node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        bridge_node.destroy_node()
        rclpy.shutdown()

async def main():
    """主函数"""
    loop = asyncio.get_running_loop()  # 获取主线程的事件循环
    
    # 在后台线程启动ROS2节点，并传递事件循环
    ros2_thread = threading.Thread(target=run_ros2_node, args=(loop,), daemon=True)
    ros2_thread.start()
    
    # 等待ROS2节点初始化
    await asyncio.sleep(2)
    
    # 启动WebSocket服务器
    logger.info("Starting WebSocket server on ws://localhost:9090")
    server = await websockets.serve(handle_websocket_client, "localhost", 9090)
    
    # 保持服务器运行
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down WebSocket bridge...")