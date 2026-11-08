"""Enrollment never enables input before explicit approval; no OS input used."""
import asyncio
import json
import secrets
import tempfile
import unittest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from server.pairing import (PairingManager, DiscoveryResponder, commitment, public_bytes,
                            verification_number, encode_message, decode_message)
from server.protocol import (HEADER_SIZE, PKT_PAIRING, PKT_HANDSHAKE, pack_packet, unpack_header)
from server.security import load_identity
from server.server import SPenServer


class PairingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.identity=load_identity(self.directory.name)
        self.manager=PairingManager(self.identity,0,desktop_name='Test desktop',lan_address='192.168.1.15',approval_seconds=1.0)
        self.server=SPenServer(None,host='127.0.0.1',port=0,tls_context=self.identity.server_context(),pairing_code=self.identity.pairing_code,pairing_manager=self.manager,discovery_port=0)
        await self.server.start()
        self.writers=[]

    async def asyncTearDown(self):
        await self.server.stop()
        for writer in self.writers:
            writer.close()
            try:await writer.wait_closed()
            except (OSError,asyncio.TimeoutError):pass
        self.directory.cleanup()

    async def packet(self,reader):
        header=await asyncio.wait_for(reader.readexactly(HEADER_SIZE),1)
        kind,seq,size=unpack_header(header)
        return kind,seq,await asyncio.wait_for(reader.readexactly(size),1)

    async def connect(self):
        reader,writer=await asyncio.open_connection('127.0.0.1',self.server.bound_endpoint[1],ssl=self.identity.client_context(),server_hostname='localhost')
        self.writers.append(writer)
        kind,_,_=await self.packet(reader)
        self.assertEqual(kind,PKT_HANDSHAKE)
        return reader,writer

    async def enrollment(self, *, tamper=False, on_number=None):
        reader,writer=await self.connect()
        key=ec.generate_private_key(ec.SECP256R1());public=public_bytes(key);nonce=secrets.token_bytes(32)
        writer.write(pack_packet(PKT_PAIRING,0,encode_message({'stage':'request','name':'My tablet','commitment':commitment('client',public,nonce).hex()})));await writer.drain()
        _,seq,data=await self.packet(reader);challenge=decode_message(data);self.assertEqual(seq,0)
        writer.write(pack_packet(PKT_PAIRING,1,encode_message({'stage':'client_reveal','public_key':public.hex(),'nonce':(b'0'*32 if tamper else nonce).hex()})));await writer.drain()
        _,_,data=await self.packet(reader);reveal=decode_message(data)
        server_public=bytes.fromhex(reveal['public_key']);server_nonce=bytes.fromhex(reveal['nonce'])
        self.assertEqual(commitment('server',server_public,server_nonce).hex(),challenge['commitment'])
        secret=key.exchange(ec.ECDH(),serialization.load_der_public_key(server_public))
        number=verification_number(secret,self.identity.fingerprint,public,nonce,server_public,server_nonce)
        if on_number:on_number(number)
        _,_,data=await self.packet(reader)
        return decode_message(data)

    async def test_closed_window_cannot_enroll_or_own_input(self):
        with self.assertRaises(asyncio.IncompleteReadError):await self.enrollment()
        self.assertIsNone(self.server._owner)
        self.assertFalse(self.server.active_clients)

    async def test_credentials_are_sent_only_after_matching_number_is_approved(self):
        self.manager.open_window();requests=[]
        self.manager.on_request=requests.append
        def approve(number):
            self.assertEqual(requests[0].number,number)
            self.manager.decide(requests[0].token,True)
        result=await self.enrollment(on_number=approve)
        self.assertTrue(result['approved']);self.assertEqual(result['pairing_code'],self.identity.pairing_code)
        self.assertEqual(result['fingerprint'],self.identity.fingerprint)
        self.assertEqual(result['host'],'192.168.1.15')
        self.assertIsNone(self.server._owner);self.assertFalse(self.manager.is_open)

    async def test_denied_request_does_not_receive_credentials(self):
        self.manager.open_window()
        self.manager.on_request=lambda request:self.manager.decide(request.token,False)
        result=await self.enrollment()
        self.assertEqual(result,{'stage':'result','approved':False})
        self.assertIsNone(self.server._owner)

    async def test_changed_commitment_cannot_prompt_or_enroll(self):
        self.manager.open_window();requests=[];self.manager.on_request=requests.append
        with self.assertRaises(asyncio.IncompleteReadError):await self.enrollment(tamper=True)
        self.assertEqual(requests,[]);self.assertIsNone(self.server._owner)

    async def test_approval_timeout_clears_pending_request(self):
        self.manager.approval_seconds=.05
        self.manager.open_window()
        with self.assertRaises(asyncio.IncompleteReadError):await self.enrollment()
        self.assertIsNone(self.manager._token);self.assertIsNone(self.manager._decision)

    async def test_cancelled_window_and_stale_approval_do_not_release_credentials(self):
        self.manager.open_window()
        def cancel(request):
            self.manager.cancel();self.manager.decide(request.token,True)
        self.manager.on_request=cancel
        result=await self.enrollment()
        self.assertFalse(result['approved']);self.assertNotIn('pairing_code',result)

    async def test_enrollment_does_not_displace_existing_input_owner(self):
        self.manager.open_window()
        owner = object()
        self.server._owner = owner
        self.manager.on_request=lambda request:self.manager.decide(request.token,True)
        result=await self.enrollment()
        self.assertTrue(result['approved']);self.assertIs(self.server._owner,owner)
        self.server._owner=None

    async def test_phone_disconnect_clears_request_before_timeout(self):
        self.manager.open_window()
        def disconnect(number):self.writers[-1].close()
        with self.assertRaises(asyncio.IncompleteReadError):await self.enrollment(on_number=disconnect)
        for _ in range(30):
            if self.manager._token is None:break
            await asyncio.sleep(.005)
        self.assertIsNone(self.manager._token)

    async def test_rate_limited_window_rejects_additional_enrollment(self):
        self.manager.open_window();self.manager.attempts=5
        with self.assertRaises(asyncio.IncompleteReadError):await self.enrollment()
        self.assertIsNone(self.manager._token)

    def test_discovery_is_silent_until_pairing_is_open(self):
        class Transport:
            def __init__(self):self.sent=[]
            def sendto(self,data,address):self.sent.append((data,address))
        responder=DiscoveryResponder(self.manager);transport=Transport();responder.connection_made(transport)
        query=json.dumps({'service':'spen-bridge','version':1,'probe':'ab'*16}).encode()
        responder.datagram_received(query,('192.168.1.2',43123));self.assertEqual(transport.sent,[])
        self.manager.open_window();responder.datagram_received(query,('192.168.1.2',43123))
        reply=json.loads(transport.sent[0][0]);self.assertEqual(reply['probe'],'ab'*16)
        self.assertNotIn('pairing_code',reply);self.assertNotIn('fingerprint',reply)

    def test_certificate_change_changes_verification_and_commitments_are_role_bound(self):
        public=b'public';nonce=b'x'*32
        self.assertNotEqual(commitment('client',public,nonce),commitment('server',public,nonce))
        self.assertNotEqual(verification_number(b's'*32,'01'*32,public,nonce,public,nonce),
                            verification_number(b's'*32,'02'*32,public,nonce,public,nonce))
        expected=verification_number(bytes(range(32)),'ab'*32,b'client-public',b'c'*32,b'server-public',b's'*32)
        self.assertEqual(expected,'487673')  # Shared with the Android JVM test.
