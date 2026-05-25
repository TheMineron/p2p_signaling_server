(function () {
    const joinScreen = document.getElementById('join-screen');
    const roomScreen = document.getElementById('room-screen');
    const nicknameInput = document.getElementById('nickname');
    const roomIdInput = document.getElementById('roomId');
    const roomPasswordInput = document.getElementById('roomPassword');
    const joinBtn = document.getElementById('joinBtn');
    const videoGrid = document.getElementById('videoGrid');
    const roomTitle = document.getElementById('roomTitle');
    const roleBadge = document.getElementById('roleBadge');
    const leaveBtn = document.getElementById('leaveBtn');
    const micBtn = document.getElementById('micBtn');
    const camBtn = document.getElementById('camBtn');
    const screenBtn = document.getElementById('screenBtn');
    const settingsBtn = document.getElementById('settingsBtn');
    const muteAllBtn = document.getElementById('muteAllBtn');
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendChatBtn = document.getElementById('sendChatBtn');
    const replyPreview = document.getElementById('replyPreview');
    const replyText = document.getElementById('replyText');
    const cancelReply = document.getElementById('cancelReply');
    const participantsList = document.getElementById('participantsList');

    let ws = null;
    let localStream = null;
    let currentRoomId = null;
    let currentNickname = null;
    let currentParticipantId = null;
    let currentRole = 'participant';
    let iceServers = [];
    let pcConfig = {iceServers: [{urls: 'stun:stun.l.google.com:19302'}]};

    const peers = new Map();
    const participantsInfo = new Map();
    let chatHistory = [];
    let replyToMessageId = null;
    let localAudioEnabled = true;
    let localVideoEnabled = true;
    let localScreenShare = false;
    let originalVideoTrack = null;
    let screenTrack = null;

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const tab = btn.dataset.tab;
            document.getElementById('chatPanel').classList.toggle('active', tab === 'chat');
            document.getElementById('participantsPanel').classList.toggle('active', tab === 'participants');
        });
    });

    function connectWebSocket(roomId, nickname, password) {
        const wsUrl = `wss://${window.location.host}/ws`;
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
            console.log('[WS] Connected');
            sendJoin(roomId, nickname, password);
        };
        ws.onmessage = async (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log('[WS] Received:', msg.type, msg);
                await handleMessage(msg);
            } catch (e) {
                console.error('[WS] Parse error:', e);
            }
        };
        ws.onerror = (err) => console.error('[WS] Error:', err);
        ws.onclose = () => {
            console.log('[WS] Closed');
            cleanupAll();
            joinScreen.style.display = 'block';
            roomScreen.style.display = 'none';
        };
    }

    function sendJson(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(obj));
        }
    }

    function sendJoin(room, nickname, password) {
        const req = {type: 'join', room, nickname};
        if (password) req.password = password;
        sendJson(req);
    }

    function sendSignal(targetId, data) {
        sendJson({type: 'signal', target_id: targetId, data});
    }

    function sendPing() {
        sendJson({type: 'ping', timestamp: Date.now()});
    }

    async function handleMessage(msg) {
        switch (msg.type) {
            case 'joined':
                currentRoomId = msg.room;
                currentNickname = msg.nickname;
                currentParticipantId = msg.participant_id;
                currentRole = msg.role;
                participantsInfo.set(currentParticipantId, {
                    id: currentParticipantId,
                    name: currentNickname,
                    role: currentRole,
                    audio_enabled: localAudioEnabled,
                    video_enabled: localVideoEnabled,
                    screen_share: false
                });
                updateParticipantsUI();
                if (msg.ice_servers && msg.ice_servers.length) {
                    iceServers = msg.ice_servers;
                    pcConfig = {iceServers};
                }
                roomTitle.textContent = `Комната: ${currentRoomId}`;
                roleBadge.textContent = currentRole === 'moderator' ? 'Модератор' : 'Участник';
                muteAllBtn.style.display = currentRole === 'moderator' ? 'inline-block' : 'none';
                joinScreen.style.display = 'none';
                roomScreen.style.display = 'flex';
                await initLocalMedia();
                break;

            case 'existing_participants':
                msg.participants.forEach(p => {
                    participantsInfo.set(p.id, {
                        id: p.id,
                        name: p.name,
                        role: p.role,
                        audio_enabled: p.audio_enabled,
                        video_enabled: p.video_enabled,
                        screen_share: false
                    });
                });
                updateParticipantsUI();
                break;

            case 'participant_joined':
                if (msg.participant.id === currentParticipantId) break;

                participantsInfo.set(msg.participant.id, {
                    id: msg.participant.id,
                    name: msg.participant.name,
                    role: msg.participant.role,
                    audio_enabled: msg.participant.audio_enabled,
                    video_enabled: msg.participant.video_enabled,
                    screen_share: false
                });
                updateParticipantsUI();
                await createPeerConnection(msg.participant.id, true);
                break;

            case 'participant_left':
                participantsInfo.delete(msg.participant_id);
                removePeer(msg.participant_id);
                updateParticipantsUI();
                break;

            case 'signal':
                await handleSignal(msg.from_id, msg.data);
                break;

            case 'chat_history':
                chatHistory = msg.messages || [];
                renderChatMessages();
                break;

            case 'chat_sent':
            case 'chat':
                addOrUpdateChatMessage(msg);
                break;

            case 'chat_edited':
                updateChatMessageEdit(msg);
                break;

            case 'chat_deleted':
                markChatMessageDeleted(msg.msg_id);
                break;

            case 'chat_pinned':
                setChatMessagePin(msg.msg_id, true);
                break;

            case 'chat_unpinned':
                setChatMessagePin(msg.msg_id, false);
                break;

            case 'chat_cleared':
                chatHistory = [];
                renderChatMessages();
                break;

            case 'participant_updated':
                if (participantsInfo.has(msg.participant_id)) {
                    const p = participantsInfo.get(msg.participant_id);
                    if (msg.audio_enabled !== undefined && msg.audio_enabled !== null)
                        p.audio_enabled = msg.audio_enabled;
                    if (msg.video_enabled !== undefined && msg.video_enabled !== null)
                        p.video_enabled = msg.video_enabled;
                    updateParticipantsUI();
                }
                break;

            case 'participant_renamed':
                if (participantsInfo.has(msg.participant_id)) {
                    participantsInfo.get(msg.participant_id).name = msg.new_name;
                    updateParticipantsUI();
                }
                break;

            case 'screen_share_state':
                if (participantsInfo.has(msg.participant_id)) {
                    participantsInfo.get(msg.participant_id).screen_share = msg.enabled;
                    updateParticipantsUI();
                }
                break;

            case 'force_mute':
                setLocalAudio(false);
                break;

            case 'force_unmute':
                setLocalAudio(true);
                break;

            case 'kicked':
                alert(`Вас исключили из комнаты. ${msg.reason ? 'Причина: ' + msg.reason : ''}`);
                ws.close();
                break;

            case 'all_muted':
                alert('Модератор отключил микрофоны у всех участников.');
                break;

            case 'room_limit_updated':
                alert(`Лимит участников изменён: ${msg.limit !== null ? msg.limit : 'без ограничений'}`);
                break;

            case 'pong':
                break;

            case 'error':
                alert(`Ошибка: ${msg.message}`);
                break;

            default:
                console.warn('[WS] Unknown message type:', msg.type);
        }
    }

    async function initLocalMedia() {
        try {
            localStream = await navigator.mediaDevices.getUserMedia({video: true, audio: true});
            addLocalVideoContainer(localStream);
            localAudioEnabled = true;
            localVideoEnabled = true;
            updateMediaButtons();

            for (const [remoteId, peerInfo] of peers.entries()) {
                localStream.getTracks().forEach(track => peerInfo.pc.addTrack(track, localStream));

                if (peerInfo.pc.signalingState === 'stable' && peerInfo.pc.remoteDescription) {
                    const offer = await peerInfo.pc.createOffer();
                    await peerInfo.pc.setLocalDescription(offer);
                    sendSignal(remoteId, {type: 'offer', sdp: offer.sdp});
                }
            }
        } catch (e) {
            console.error('getUserMedia error:', e);
            alert('Не удалось получить доступ к камере/микрофону');
        }
    }

    function addLocalVideoContainer(stream) {
        const container = document.createElement('div');
        container.className = 'video-container local';
        container.id = 'local-video';
        const video = document.createElement('video');
        video.autoplay = true;
        video.playsInline = true;
        video.muted = true;
        video.srcObject = stream;
        container.appendChild(video);
        const label = document.createElement('div');
        label.className = 'participant-label';
        label.innerHTML = `<span>Вы (${currentNickname})</span>`;
        container.appendChild(label);
        videoGrid.appendChild(container);
    }

    function setLocalAudio(enabled) {
        if (localStream) {
            localStream.getAudioTracks().forEach(track => track.enabled = enabled);
            localAudioEnabled = enabled;
            updateMediaButtons();
        }
        if (!enabled) {
            sendJson({type: 'set_audio_enabled', enabled: false});
        } else {
            sendJson({type: 'set_audio_enabled', enabled: true});
        }
    }

    function setLocalVideo(enabled) {
        if (localStream) {
            localStream.getVideoTracks().forEach(track => track.enabled = enabled);
            localVideoEnabled = enabled;
            updateMediaButtons();
        }
        sendJson({type: 'set_video_enabled', enabled});
    }

    async function toggleScreenShare() {
        if (localScreenShare) {
            if (screenTrack) {
                screenTrack.stop();
                screenTrack = null;
            }
            if (originalVideoTrack) {
                replaceVideoTrackInAllPeers(originalVideoTrack);
                originalVideoTrack = null;
            }
            localScreenShare = false;
            screenBtn.classList.remove('active');
            sendJson({type: 'request_screen_share', enabled: false});
        } else {
            try {
                const screenStream = await navigator.mediaDevices.getDisplayMedia({video: true});
                screenTrack = screenStream.getVideoTracks()[0];
                originalVideoTrack = localStream.getVideoTracks()[0] || null;
                replaceVideoTrackInAllPeers(screenTrack);
                if (originalVideoTrack) {
                    localStream.removeTrack(originalVideoTrack);
                    originalVideoTrack.stop();
                }
                localStream.addTrack(screenTrack);
                localScreenShare = true;
                screenBtn.classList.add('active');
                sendJson({type: 'request_screen_share', enabled: true});
                screenTrack.onended = () => {
                    toggleScreenShare();
                };
            } catch (e) {
                console.error('Screen share error:', e);
            }
        }
    }

    function replaceVideoTrackInAllPeers(newTrack) {
        for (const [, peerInfo] of peers.entries()) {
            const sender = peerInfo.pc.getSenders().find(s => s.track && s.track.kind === 'video');
            if (sender) sender.replaceTrack(newTrack);
        }
    }

    function updateMediaButtons() {
        micBtn.classList.toggle('off', !localAudioEnabled);
        camBtn.classList.toggle('off', !localVideoEnabled);
    }

    async function createPeerConnection(remoteId, isInitiator) {
        if (peers.has(remoteId)) {
            // Avoid duplicates – in a correct flow this should never happen
            console.warn('[WebRTC] Peer already exists for', remoteId);
            return;
        }
        const pc = new RTCPeerConnection(pcConfig);
        const container = document.createElement('div');
        container.className = 'video-container';
        container.id = `remote-${remoteId}`;
        const video = document.createElement('video');
        video.autoplay = true;
        video.playsInline = true;
        container.appendChild(video);
        const label = document.createElement('div');
        label.className = 'participant-label';
        const pInfo = participantsInfo.get(remoteId) || {name: remoteId.slice(0, 6)};
        label.innerHTML = `<span>${pInfo.name}</span>`;
        container.appendChild(label);
        videoGrid.appendChild(container);

        const peerInfo = {
            pc,
            videoElement: video,
            container,
            stream: null,
            pendingCandidates: []
        };
        peers.set(remoteId, peerInfo);

        if (localStream) {
            localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
        }

        pc.onicecandidate = (event) => {
            if (event.candidate) {
                sendSignal(remoteId, {type: 'ice-candidate', candidate: event.candidate});
            }
        };

        pc.ontrack = (event) => {
            if (peerInfo.videoElement.srcObject !== event.streams[0]) {
                peerInfo.videoElement.srcObject = event.streams[0];
                peerInfo.stream = event.streams[0];
            }
        };

        pc.oniceconnectionstatechange = () => {
            if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed') {
                removePeer(remoteId);
            }
        };

        if (isInitiator) {
            try {
                const offer = await pc.createOffer();
                await pc.setLocalDescription(offer);
                sendSignal(remoteId, {type: 'offer', sdp: offer.sdp});
            } catch (e) {
                console.error('createOffer error:', e);
            }
        }
    }

    async function handleSignal(fromId, signalData) {
        let peerInfo = peers.get(fromId);
        if (!peerInfo && signalData.type === 'offer') {
            await createPeerConnection(fromId, false);
            peerInfo = peers.get(fromId);
        }
        if (!peerInfo) return;

        const pc = peerInfo.pc;
        try {
            if (signalData.type === 'offer') {
                await pc.setRemoteDescription(new RTCSessionDescription({type: 'offer', sdp: signalData.sdp}));
                for (const cand of peerInfo.pendingCandidates) await pc.addIceCandidate(cand);
                peerInfo.pendingCandidates = [];
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                sendSignal(fromId, {type: 'answer', sdp: answer.sdp});
            } else if (signalData.type === 'answer') {
                await pc.setRemoteDescription(new RTCSessionDescription({type: 'answer', sdp: signalData.sdp}));
                for (const cand of peerInfo.pendingCandidates) await pc.addIceCandidate(cand);
                peerInfo.pendingCandidates = [];
            } else if (signalData.type === 'ice-candidate' && signalData.candidate) {
                const candidate = new RTCIceCandidate(signalData.candidate);
                if (pc.remoteDescription) {
                    await pc.addIceCandidate(candidate);
                } else {
                    peerInfo.pendingCandidates.push(candidate);
                }
            }
        } catch (e) {
            console.error('Signal handling error:', e);
        }
    }

    function removePeer(remoteId) {
        const peerInfo = peers.get(remoteId);
        if (peerInfo) {
            peerInfo.pc.close();
            if (peerInfo.container) peerInfo.container.remove();
            peers.delete(remoteId);
        }
        participantsInfo.delete(remoteId);
        updateParticipantsUI();
    }

    function cleanupAll() {
        for (const [, peerInfo] of peers.entries()) {
            peerInfo.pc.close();
            if (peerInfo.container) peerInfo.container.remove();
        }
        peers.clear();
        if (localStream) {
            localStream.getTracks().forEach(t => t.stop());
            localStream = null;
        }
        const localContainer = document.getElementById('local-video');
        if (localContainer) localContainer.remove();
        participantsInfo.clear();
        chatHistory = [];
        renderChatMessages();
    }

    function addOrUpdateChatMessage(msg) {
        const existing = chatHistory.find(m => m.msg_id === msg.msg_id);
        if (existing) {
            Object.assign(existing, msg);
        } else {
            chatHistory.push(msg);
        }
        renderChatMessages();
    }

    function updateChatMessageEdit(msg) {
        const found = chatHistory.find(m => m.msg_id === msg.msg_id);
        if (found) {
            found.text = msg.text;
            found.edited = true;
            renderChatMessages();
        }
    }

    function markChatMessageDeleted(msgId) {
        const found = chatHistory.find(m => m.msg_id === msgId);
        if (found) {
            found.deleted = true;
            renderChatMessages();
        }
    }

    function setChatMessagePin(msgId, pinned) {
        const found = chatHistory.find(m => m.msg_id === msgId);
        if (found) {
            found.is_pinned = pinned;
            renderChatMessages();
        }
    }

    function renderChatMessages() {
        chatMessages.innerHTML = '';
        const sorted = [...chatHistory].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        for (const msg of sorted) {
            const div = document.createElement('div');
            div.className = 'chat-message';
            if (msg.deleted) div.classList.add('deleted');
            if (msg.is_pinned) div.classList.add('pinned');
            const header = document.createElement('div');
            header.className = 'msg-header';
            header.innerHTML = `<span><b>${escapeHtml(msg.from_name)}</b></span><span>${formatTime(msg.timestamp)}</span>`;
            const text = document.createElement('div');
            text.className = 'msg-text';
            text.textContent = msg.deleted ? 'Сообщение удалено' : msg.text;
            if (msg.edited && !msg.deleted) text.textContent += ' (ред.)';
            if (msg.reply_to_msg_id) {
                const replied = chatHistory.find(m => m.msg_id === msg.reply_to_msg_id);
                if (replied) {
                    const replyInfo = document.createElement('div');
                    replyInfo.style.fontSize = '0.7rem';
                    replyInfo.style.color = '#aaa';
                    replyInfo.textContent = `↪ ${replied.from_name}: ${replied.text.substring(0, 30)}`;
                    div.prepend(replyInfo);
                }
            }
            div.appendChild(header);
            div.appendChild(text);

            if (!msg.deleted) {
                const actions = document.createElement('div');
                actions.className = 'msg-actions';
                const replyBtn = document.createElement('button');
                replyBtn.textContent = '↩';
                replyBtn.title = 'Ответить';
                replyBtn.onclick = () => setReplyTo(msg.msg_id, msg.from_name, msg.text);
                actions.appendChild(replyBtn);

                if (msg.from_id === currentParticipantId) {
                    const editBtn = document.createElement('button');
                    editBtn.textContent = '✎';
                    editBtn.title = 'Редактировать';
                    editBtn.onclick = () => {
                        const newText = prompt('Новый текст:', msg.text);
                        if (newText && newText.trim()) {
                            sendJson({type: 'chat_edit', msg_id: msg.msg_id, text: newText.trim()});
                        }
                    };
                    actions.appendChild(editBtn);
                    const delBtn = document.createElement('button');
                    delBtn.textContent = '🗑';
                    delBtn.title = 'Удалить';
                    delBtn.onclick = () => {
                        if (confirm('Удалить сообщение?')) sendJson({type: 'chat_delete', msg_id: msg.msg_id});
                    };
                    actions.appendChild(delBtn);
                } else if (currentRole === 'moderator') {
                    const delBtn = document.createElement('button');
                    delBtn.textContent = '🗑';
                    delBtn.title = 'Удалить (модер)';
                    delBtn.onclick = () => sendJson({type: 'chat_delete', msg_id: msg.msg_id});
                    actions.appendChild(delBtn);
                }
                if (currentRole === 'moderator') {
                    const pinBtn = document.createElement('button');
                    pinBtn.textContent = msg.is_pinned ? '📌' : '📍';
                    pinBtn.title = msg.is_pinned ? 'Открепить' : 'Закрепить';
                    pinBtn.onclick = () => {
                        if (msg.is_pinned) sendJson({type: 'chat_unpin', msg_id: msg.msg_id});
                        else sendJson({type: 'chat_pin', msg_id: msg.msg_id});
                    };
                    actions.appendChild(pinBtn);
                }
                div.appendChild(actions);
            }
            chatMessages.appendChild(div);
        }
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function setReplyTo(msgId, fromName, text) {
        replyToMessageId = msgId;
        replyText.textContent = `Ответ ${fromName}: ${text.substring(0, 20)}...`;
        replyPreview.style.display = 'flex';
        chatInput.focus();
    }

    function escapeHtml(text) {
        const map = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'};
        return String(text).replace(/[&<>"']/g, m => map[m]);
    }

    function formatTime(ts) {
        if (!ts) return '';
        const d = new Date(ts * 1000);
        return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    }

    function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        const payload = {type: 'chat_send', text};
        if (replyToMessageId) {
            payload.type = 'chat_reply';
            payload.reply_to_msg_id = replyToMessageId;
            replyToMessageId = null;
            replyPreview.style.display = 'none';
        }
        sendJson(payload);
        chatInput.value = '';
    }

    function updateParticipantsUI() {
        participantsList.innerHTML = '';
        for (const [id, p] of participantsInfo.entries()) {
            const div = document.createElement('div');
            div.className = 'participant-item';
            const info = document.createElement('div');
            info.className = 'participant-info';
            let micIcon = p.audio_enabled ? '🎤' : '🔇';
            let camIcon = p.video_enabled ? '📹' : '📷❌';
            if (p.screen_share) camIcon = '🖥️';
            info.innerHTML = `<span>${micIcon} ${camIcon}</span> <span class="participant-name">${escapeHtml(p.name)}</span>`;
            const actions = document.createElement('div');
            actions.className = 'participant-actions';
            if (currentRole === 'moderator' && id !== currentParticipantId) {
                const muteBtn = document.createElement('button');
                muteBtn.textContent = p.audio_enabled ? '🔇' : '🎤';
                muteBtn.title = p.audio_enabled ? 'Заглушить' : 'Включить микрофон';
                muteBtn.onclick = () => {
                    if (p.audio_enabled) sendJson({type: 'mute_participant', target_id: id});
                    else sendJson({type: 'unmute_participant', target_id: id});
                };
                actions.appendChild(muteBtn);
                const kickBtn = document.createElement('button');
                kickBtn.textContent = '🚫';
                kickBtn.title = 'Исключить';
                kickBtn.onclick = () => {
                    const reason = prompt('Причина (необязательно):');
                    sendJson({type: 'kick_participant', target_id: id, reason: reason || null});
                };
                actions.appendChild(kickBtn);
            }
            div.appendChild(info);
            div.appendChild(actions);
            participantsList.appendChild(div);
        }
    }

    micBtn.addEventListener('click', () => setLocalAudio(!localAudioEnabled));
    camBtn.addEventListener('click', () => setLocalVideo(!localVideoEnabled));
    screenBtn.addEventListener('click', toggleScreenShare);
    settingsBtn.addEventListener('click', () => {
        const newNick = prompt('Новый никнейм:', currentNickname);
        if (newNick && newNick.trim()) {
            sendJson({type: 'set_nickname', nickname: newNick.trim()});
            currentNickname = newNick.trim();
            const localLabel = document.querySelector('#local-video .participant-label span');
            if (localLabel) localLabel.textContent = `Вы (${currentNickname})`;
        }
    });
    muteAllBtn.addEventListener('click', () => {
        if (currentRole === 'moderator') sendJson({type: 'mute_all'});
    });
    leaveBtn.addEventListener('click', () => {
        sendJson({type: 'leave'});
        ws.close();
    });
    sendChatBtn.addEventListener('click', sendChatMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });
    cancelReply.addEventListener('click', () => {
        replyToMessageId = null;
        replyPreview.style.display = 'none';
    });
    joinBtn.addEventListener('click', () => {
        const nick = nicknameInput.value.trim();
        const room = roomIdInput.value.trim();
        if (!nick || !room) return alert('Введите имя и ID комнаты');
        connectWebSocket(room, nick, roomPasswordInput.value.trim() || undefined);
    });

    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) sendPing();
    }, 25000);

    function updateVideoLayout() {
        const grid = videoGrid;
        if (!grid) return;

        const containers = grid.querySelectorAll('.video-container');
        const count = containers.length;
        if (count === 0) return;

        const gridStyle = getComputedStyle(grid);
        const paddingLeft = parseFloat(gridStyle.paddingLeft) || 0;
        const paddingRight = parseFloat(gridStyle.paddingRight) || 0;
        const paddingTop = parseFloat(gridStyle.paddingTop) || 0;
        const paddingBottom = parseFloat(gridStyle.paddingBottom) || 0;
        const gap = parseFloat(gridStyle.gap) || parseFloat(gridStyle.columnGap) || 8; // gap между элементами

        const availableWidth = grid.clientWidth - paddingLeft - paddingRight;
        const availableHeight = grid.clientHeight - paddingTop - paddingBottom;

        if (availableWidth <= 0 || availableHeight <= 0) return;

        let bestCols = 1;
        let bestArea = 0;
        let bestWidth = 0;
        let bestHeight = 0;

        for (let cols = 1; cols <= count; cols++) {
            const rows = Math.ceil(count / cols);
            const totalHGap = (cols - 1) * gap;
            const totalVGap = (rows - 1) * gap;

            const cellWidth = Math.floor((availableWidth - totalHGap) / cols);
            const cellHeight = Math.floor((availableHeight - totalVGap) / rows);

            const widthByHeight = cellHeight * 4 / 3;
            const heightByWidth = cellWidth * 3 / 4;

            const realWidth = Math.min(cellWidth, widthByHeight);
            const realHeight = Math.min(cellHeight, heightByWidth);

            const area = realWidth * realHeight * 0.8;
            if (area > bestArea) {
                bestArea = area;
                bestCols = cols;
                bestWidth = realWidth;
                bestHeight = realHeight;
            }
        }

        containers.forEach(container => {
            container.style.width = bestWidth + 'px';
            container.style.height = bestHeight + 'px';
        });
    }

    const observer = new MutationObserver(updateVideoLayout);
    observer.observe(videoGrid, {childList: true});

    window.addEventListener('resize', updateVideoLayout);
})();


