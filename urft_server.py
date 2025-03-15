#!/usr/bin/env python3
import sys
import socket
import struct

def main():
    if len(sys.argv) != 3:
        print("Usage: python urft_server.py <server_ip> <server_port>")
        sys.exit(1)
        
    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    
    # สร้าง UDP socket และ bind ไปยัง IP และ port ที่ระบุ
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((server_ip, server_port))
    print("Server is running on {}:{}".format(server_ip, server_port))
    
    expected_seq = 0  # คาดหวัง sequence number ที่จะได้รับ
    file_handle = None
    client_addr = None

    while True:
        data, addr = sock.recvfrom(4096)
        if client_addr is None:
            client_addr = addr  # รับเฉพาะการติดต่อจาก client รายแรก
        if len(data) < 5:
            continue
        
        # header: 4 ไบต์สำหรับ sequence number และ 1 ไบต์สำหรับ packet type
        seq, packet_type = struct.unpack("!IB", data[:5])
        payload = data[5:]
        
        # ประมวลผล packet ตามประเภท
        if packet_type == 0:  # Packet ชื่อไฟล์
            if seq == 0:
                file_name = payload.decode('utf-8')
                # สร้างโฟลเดอร์ "src" ถ้ายังไม่มี
                import os
                folder = "src"
                if not os.path.exists(folder):
                    os.mkdir(folder)
                # รวม path ของโฟลเดอร์กับชื่อไฟล์
                file_path = os.path.join(folder, file_name)
                print("Receiving file:", file_path)
                try:
                    file_handle = open(file_path, 'wb')
                except Exception as e:
                    print("Error opening file:", e)
                    sys.exit(1)
                expected_seq = 1  # กำหนด sequence ที่คาดหวังถัดไปเป็น 1
            # ส่ง ACK (packet type 3)
            ack_packet = struct.pack("!IB", seq, 3)
            sock.sendto(ack_packet, addr)
            
        elif packet_type == 1:  # Packet ข้อมูลไฟล์
            if seq == expected_seq and file_handle is not None:
                file_handle.write(payload)
                expected_seq += 1
            # ส่ง ACK สำหรับ packet นี้ (แม้จะเป็น packet ซ้ำ)
            ack_packet = struct.pack("!IB", seq, 3)
            sock.sendto(ack_packet, addr)
            
        elif packet_type == 2:  # Packet สัญญาณจบไฟล์ (EOF)
            if file_handle:
                file_handle.close()
                print("File received successfully.")
                file_handle = None
            # ส่ง ACK สำหรับ EOF แล้วจบโปรแกรม
            ack_packet = struct.pack("!IB", seq, 3)
            sock.sendto(ack_packet, addr)
            break  # รับเฉพาะ client รายเดียว หลังรับไฟล์ครบแล้ว

if __name__ == "__main__":
    main()




# รับ command-line arguments สำหรับ <server_ip> และ <server_port>
# สร้าง UDP socket และ bind ไปที่ IP และ port ที่กำหนด
# รอรับ packet จาก client ซึ่งจะเริ่มจาก packet ชื่อไฟล์ (packet type 0) จากนั้นจึงรับ packet ข้อมูล (packet type 1)
# เมื่อได้รับ packet สัญญาณจบ (EOF, packet type 2) จะปิดไฟล์และออกจากโปรแกรม
# ในแต่ละ packet จะส่ง ACK (packet type 3) กลับไปยัง client โดยอิงจาก sequence number ที่ได้รับ