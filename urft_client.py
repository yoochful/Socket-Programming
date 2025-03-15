#!/usr/bin/env python3
import sys
import socket
import struct
import os
import time

# กำหนดขนาดข้อมูลในแต่ละ packet (4096 bytes)
CHUNK_SIZE = 4096
# กำหนดเวลา timeout สำหรับแต่ละ packet (วินาที)
TIMEOUT = 2.0
# กำหนดขนาด sliding window
WINDOW_SIZE = 5

# สร้าง packet โดยมี header 4 ไบต์สำหรับ sequence number และ 1 ไบต์สำหรับ packet type
def make_packet(seq, packet_type, payload=b''):
    return struct.pack("!IB", seq, packet_type) + payload

def main():
    if len(sys.argv) != 4:
        print("Usage: python urft_client.py <file_path> <server_ip> <server_port>")
        sys.exit(1)

    file_path = sys.argv[1]
    server_ip = sys.argv[2]
    server_port = int(sys.argv[3])
    server_addr = (server_ip, server_port)
    
    # สร้าง UDP socket และตั้งค่า timeout
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)
    
    # --- ส่งชื่อไฟล์ (packet type 0) แบบ Stop-and-Wait ---
    file_name = os.path.basename(file_path)
    seq = 0
    packet = make_packet(seq, 0, file_name.encode('utf-8'))
    while True:
        sock.sendto(packet, server_addr)
        try:
            data, _ = sock.recvfrom(1024)
            ack_seq, ack_type = struct.unpack("!IB", data[:5])
            if ack_type == 3 and ack_seq == seq:
                print("Received ACK for file name")
                break
        except socket.timeout:
            print("Timeout waiting for ACK for file name, resending...")
    
    # --- เตรียมข้อมูลไฟล์สำหรับส่ง (แบ่งเป็น chunks) ---
    try:
        with open(file_path, "rb") as f:
            chunks = []
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
    except Exception as e:
        print("Error reading file:", e)
        sys.exit(1)
    
    num_packets = len(chunks)
    # สำหรับ Go-Back-N: sequence สำหรับข้อมูลเริ่มที่ 1 ถึง num_packets
    base = 1          # Sequence number ของ packet ที่รอ ACK อยู่ตัวแรก
    next_seq = 1      # Sequence number ถัดไปที่จะส่ง
    # เก็บเวลาสำหรับ packet ใน window เพื่อใช้ตรวจสอบ timeout
    send_times = {}

    # ใช้ loop ส่งข้อมูลทั้งหมด
    while base <= num_packets:
        # ส่ง packet ใน window ที่ยังไม่ได้ส่ง (หรือยังไม่ได้ ACK) ตามขนาด window
        while next_seq < base + WINDOW_SIZE and next_seq <= num_packets:
            packet = make_packet(next_seq, 1, chunks[next_seq - 1])
            sock.sendto(packet, server_addr)
            send_times[next_seq] = time.time()
            print(f"Sent packet seq {next_seq}")
            next_seq += 1

        # รอรับ ACK สำหรับ packet ที่อยู่ใน window
        try:
            data, _ = sock.recvfrom(1024)
            if len(data) < 5:
                continue
            ack_seq, ack_type = struct.unpack("!IB", data[:5])
            if ack_type == 3:
                print(f"Received ACK for packet seq {ack_seq}")
                # ใน Go-Back-N ให้รับ ACK แบบ cumulative: ถ้า ACK สำหรับ packet seq X
                # หมายความว่า packetจาก base ถึง X ได้รับแล้ว
                if ack_seq >= base:
                    # ปรับ sliding window
                    for seq_num in range(base, ack_seq + 1):
                        if seq_num in send_times:
                            del send_times[seq_num]
                    base = ack_seq + 1
        except socket.timeout:
            # ตรวจสอบ timeout สำหรับ packet ที่ส่งแล้วแต่ยังไม่ได้ ACK ใน window
            current_time = time.time()
            # หาก packet ที่ base timeout ให้ retransmit ตั้งแต่ base ไปจนถึง next_seq-1
            if current_time - send_times.get(base, current_time) >= TIMEOUT:
                print(f"Timeout for packet seq {base}, retransmitting window...")
                for seq_num in range(base, next_seq):
                    packet = make_packet(seq_num, 1, chunks[seq_num - 1])
                    sock.sendto(packet, server_addr)
                    send_times[seq_num] = time.time()

    # --- ส่ง packet สัญญาณจบไฟล์ (EOF) ---
    eof_seq = num_packets + 1
    packet = make_packet(eof_seq, 2)
    while True:
        sock.sendto(packet, server_addr)
        try:
            data, _ = sock.recvfrom(1024)
            ack_seq, ack_type = struct.unpack("!IB", data[:5])
            if ack_type == 3 and ack_seq == eof_seq:
                print("Received ACK for EOF packet")
                break
        except socket.timeout:
            print("Timeout waiting for ACK for EOF packet, resending...")

    print("File sent successfully.")
    sock.close()

if __name__ == "__main__":
    main()
