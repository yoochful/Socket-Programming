#!/usr/bin/env python3
import sys
import socket
import struct
import os

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
    
    expected_seq = 0  # เริ่มต้นที่ 0 สำหรับ packet ชื่อไฟล์
    file_handle = None
    client_addr = None

    while True:
        data, addr = sock.recvfrom(65535)
        if client_addr is None:
            client_addr = addr  # รับเฉพาะ client ตัวแรก
        if len(data) < 5:
            continue
        
        # header: 4 ไบต์ sequence number, 1 ไบต์ packet type
        seq, packet_type = struct.unpack("!IB", data[:5])
        payload = data[5:]
        
        if packet_type == 0:  # ชื่อไฟล์
            if seq == 0:
                file_name = payload.decode('utf-8')
                folder = "src"
                if not os.path.exists(folder):
                    os.mkdir(folder)
                file_path = os.path.join(folder, file_name)
                print("Receiving file:", file_path)
                try:
                    file_handle = open(file_path, 'wb')
                except Exception as e:
                    print("Error opening file:", e)
                    sys.exit(1)
                expected_seq = 1  # Packet ถัดไปที่คาดหวัง
            # ส่ง ACK สำหรับชื่อไฟล์
            ack = struct.pack("!IB", seq, 3)
            sock.sendto(ack, addr)
        
        elif packet_type == 1:  # ข้อมูลไฟล์
            # สำหรับ Go-Back-N จะรับเฉพาะ packet ที่มี seq เท่ากับ expected_seq
            if seq == expected_seq and file_handle is not None:
                file_handle.write(payload)
                print(f"Received expected packet seq {seq}")
                expected_seq += 1
            else:
                # ถ้าไม่ตรง expected_seq ให้ ignore แต่ส่ง ACK สำหรับ last in-order packet
                print(f"Ignoring duplicate/out-of-order packet seq {seq} (expected {expected_seq})")
            # ส่ง ACK แบบ cumulative: ส่ง ACK สำหรับ packet ที่ได้รับล่าสุด (expected_seq - 1)
            ack = struct.pack("!IB", expected_seq - 1, 3)
            sock.sendto(ack, addr)
        
        elif packet_type == 2:  # EOF
            # ตรวจสอบว่า packet EOF มี seq ตรงกับ expected_seq หรือไม่
            if seq == expected_seq:
                if file_handle:
                    file_handle.close()
                    print("File received successfully.")
            # ส่ง ACK สำหรับ EOF
            ack = struct.pack("!IB", seq, 3)
            sock.sendto(ack, addr)
            break  # จบการรับไฟล์หลังจาก EOF

if __name__ == "__main__":
    main()
