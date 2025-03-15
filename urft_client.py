#!/usr/bin/env python3
import sys
import socket
import struct
import os

CHUNK_SIZE = 1024   
TIMEOUT = 1.0       

def send_packet(sock, addr, seq, packet_type, payload=b''):
    #สร้างและส่ง packet ด้วย header (sequence number และ packet type)
    packet = struct.pack("!IB", seq, packet_type) + payload
    sock.sendto(packet, addr)

def wait_for_ack(sock, expected_seq):
    # รอรับ ACK จาก server สำหรับ sequence number ที่ระบุ"""
    try:
        data, _ = sock.recvfrom(1024)
        if len(data) < 5:
            return False
        ack_seq, ack_type = struct.unpack("!IB", data[:5])
        return ack_type == 3 and ack_seq == expected_seq
    except socket.timeout:
        return False

def main():
    if len(sys.argv) != 4:
        print("Usage: python urft_client.py <file_path> <server_ip> <server_port>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    server_ip = sys.argv[2]
    server_port = int(sys.argv[3])
    server_addr = (server_ip, server_port)
    
    # สร้าง UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    
    # ส่ง packet ชื่อไฟล์ (packet_type = 0, seq = 0)
    file_name = os.path.basename(file_path)
    seq = 0
    while True:
        send_packet(sock, server_addr, seq, 0, file_name.encode('utf-8'))
        if wait_for_ack(sock, seq):
            break
        print("Timeout waiting for ACK for file name, resending...")
    
    # ส่ง packet ข้อมูลไฟล์ (packet_type = 1) ทีละ chunk
    seq = 1
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                while True:
                    send_packet(sock, server_addr, seq, 1, chunk)
                    if wait_for_ack(sock, seq):
                        break
                    print("Timeout waiting for ACK for packet seq", seq, "resending...")
                seq += 1
    except Exception as e:
        print("Error reading file:", e)
        sys.exit(1)
    
    # ส่ง packet สัญญาณจบไฟล์ (EOF) (packet_type = 2)
    while True:
        send_packet(sock, server_addr, seq, 2)
        if wait_for_ack(sock, seq):
            break
        print("Timeout waiting for ACK for EOF packet, resending...")
    
    print("File sent successfully.")
    sock.close()

if __name__ == "__main__":
    main()



# รับ command-line arguments สำหรับ <file_path>, <server_ip>, <server_port>
# อ่านไฟล์ในโหมด binary แล้วส่งชื่อไฟล์ไปยัง serverใน packet แรก (packet type 0, seq = 0)
# ส่งข้อมูลไฟล์ทีละ chunk ใน packet ที่มี packet type 1 พร้อมกับ sequence number ที่เพิ่มขึ้น
# หลังจากส่งข้อมูลครบแล้ว ส่ง packet สัญญาณจบ (EOF, packet type 2)
# ในแต่ละขั้นตอน ใช้กลไก stop-and-wait โดยรอ ACK จาก server หากไม่รับภายในเวลา timeout จะทำการ retransmit
# เมื่อส่งไฟล์เสร็จสิ้น โปรแกรมจะปิด socket และจบการทำงานโดยไม่มีการรับ keyboard input เพิ่มเติม