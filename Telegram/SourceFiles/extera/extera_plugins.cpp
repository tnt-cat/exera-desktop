/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#include "extera/extera_plugins.h"

#include "extera/extera_python.h"
#include "api/api_common.h"
#include "apiwrap.h"
#include "base/call_delayed.h"
#include "core/application.h"
#include "data/data_peer.h"
#include "data/data_session.h"
#include "history/history.h"
#include "lang/lang_keys.h"
#include "main/main_session.h"
#include "ui/basic_click_handlers.h"
#include "ui/layers/generic_box.h"
#include "ui/layers/show.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/widgets/labels.h"
#include "ui/wrap/vertical_layout.h"
#include "window/window_controller.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"

#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QMutex>
#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>

namespace Extera {
namespace {

constexpr auto kLogLimit = 300;
constexpr auto kAlertDismissed = -100;

QMutex LogMutex;
QStringList LogLines;
std::atomic<qint64> SelfId = 0;
base::weak_ptr<Main::Session> LastSession;
std::map<int, QPointer<Ui::GenericBox>> Alerts;
bool SendingFromPlugin = false;

void AddLog(const QString &text) {
	LOG(("Plugins: %1").arg(text));

	QMutexLocker lock(&LogMutex);
	LogLines.push_back(text);
	while (LogLines.size() > kLogLimit) {
		LogLines.pop_front();
	}
}

[[nodiscard]] Main::Session *CurrentSession() {
	if (const auto strong = LastSession.get()) {
		return strong;
	}
	return Core::App().maybePrimarySession();
}

[[nodiscard]] qint64 DialogId(not_null<PeerData*> peer) {
	const auto id = peer->id;
	return peerIsUser(id)
		? qint64(peerToUser(id).bare)
		: peerIsChat(id)
		? -qint64(peerToChat(id).bare)
		: -qint64(peerToChannel(id).bare);
}

[[nodiscard]] PeerData *PeerFromDialogId(
		not_null<Main::Session*> session,
		qint64 id) {
	auto &owner = session->data();
	if (id > 0) {
		return owner.peerLoaded(peerFromUser(UserId(BareId(id))));
	}
	const auto bare = BareId(-id);
	if (const auto channel = owner.peerLoaded(
			peerFromChannel(ChannelId(bare)))) {
		return channel;
	}
	return owner.peerLoaded(peerFromChat(ChatId(bare)));
}

[[nodiscard]] TextWithTags::Tags TagsFromJson(const QJsonArray &entities) {
	auto result = TextWithTags::Tags();
	for (const auto &value : entities) {
		const auto entity = value.toObject();
		const auto type = entity[u"type"_q].toString();
		const auto id = (type == u"bold"_q)
			? Ui::InputField::kTagBold
			: (type == u"italic"_q)
			? Ui::InputField::kTagItalic
			: (type == u"underline"_q)
			? Ui::InputField::kTagUnderline
			: (type == u"strike"_q)
			? Ui::InputField::kTagStrikeOut
			: (type == u"code"_q)
			? Ui::InputField::kTagCode
			: (type == u"pre"_q)
			? Ui::InputField::kTagPre
			: (type == u"spoiler"_q)
			? Ui::InputField::kTagSpoiler
			: (type == u"quote"_q)
			? Ui::InputField::kTagBlockquote
			: (type == u"url"_q)
			? entity[u"url"_q].toString()
			: QString();
		if (!id.isEmpty()) {
			result.push_back(TextWithTags::Tag{
				entity[u"offset"_q].toInt(),
				entity[u"length"_q].toInt(),
				id,
			});
		}
	}
	return result;
}

void SendFromPlugin(const QJsonObject &data) {
	const auto session = CurrentSession();
	const auto text = data[u"text"_q].toString();
	if (!session || text.isEmpty()) {
		return;
	}
	const auto id = qint64(data[u"peer"_q].toDouble());
	const auto peer = PeerFromDialogId(session, id);
	if (!peer) {
		AddLog(u"send_message: chat %1 is not loaded"_q.arg(id));
		return;
	}
	const auto history = session->data().history(peer->id);
	auto message = Api::MessageToSend(Api::SendAction(history));
	message.action.clearDraft = false;
	message.textWithTags = TextWithTags{
		text,
		TagsFromJson(data[u"entities"_q].toArray()),
	};
	SendingFromPlugin = true;
	session->api().sendMessage(std::move(message));
	SendingFromPlugin = false;
}

void AlertBox(not_null<Ui::GenericBox*> box, int id, QJsonObject data) {
	const auto title = data[u"title"_q].toString();
	const auto message = data[u"message"_q].toString();
	const auto items = data[u"items"_q].toArray();
	const auto buttons = data[u"buttons"_q].toArray();
	const auto answered = box->lifetime().make_state<bool>(false);
	const auto answer = [=](int which) {
		*answered = true;
		PluginsRequest(u"alert_click"_q, QJsonObject{
			{ u"id"_q, id },
			{ u"which"_q, which },
		});
		box->closeBox();
	};

	if (!title.isEmpty()) {
		box->setTitle(title);
	}
	if (!message.isEmpty()) {
		box->addRow(object_ptr<Ui::FlatLabel>(box, message, st::boxLabel));
	}
	const auto container = box->verticalLayout();
	auto index = 0;
	for (const auto &item : items) {
		const auto button = container->add(object_ptr<Ui::SettingsButton>(
			container,
			rpl::single(item.toString()),
			st::settingsButtonNoIcon));
		button->setClickedCallback([=] { answer(index); });
		++index;
	}
	for (const auto &entry : buttons) {
		const auto pair = entry.toArray();
		const auto which = pair.at(0).toInt();
		box->addButton(
			rpl::single(pair.at(1).toString()),
			[=] { answer(which); });
	}
	if (buttons.isEmpty()) {
		box->addButton(tr::lng_close(), [=] { box->closeBox(); });
	}

	Alerts[id] = box.get();
	box->boxClosing(
	) | rpl::on_next([=] {
		Alerts.erase(id);
		if (!*answered) {
			*answered = true;
			PluginsRequest(u"alert_click"_q, QJsonObject{
				{ u"id"_q, id },
				{ u"which"_q, kAlertDismissed },
			});
		}
	}, box->lifetime());
}

void HandleOnMain(const QString &name, const QJsonObject &data) {
	if (!Core::IsAppLaunched()) {
		return;
	}
	const auto window = Core::App().activeWindow()
		? Core::App().activeWindow()
		: Core::App().activePrimaryWindow();
	if (name == u"ui_post"_q) {
		const auto token = data[u"token"_q].toInt();
		const auto run = [=] {
			PluginsRequest(u"ui_run"_q, QJsonObject{ { u"token"_q, token } });
		};
		if (const auto delay = data[u"delay"_q].toInt(); delay > 0) {
			base::call_delayed(crl::time(delay), run);
		} else {
			run();
		}
	} else if (name == u"toast"_q) {
		if (window) {
			window->uiShow()->showToast(data[u"text"_q].toString());
		}
	} else if (name == u"alert"_q) {
		if (window) {
			window->uiShow()->showBox(
				Box(AlertBox, data[u"id"_q].toInt(), data));
		}
	} else if (name == u"alert_close"_q) {
		const auto i = Alerts.find(data[u"id"_q].toInt());
		if (i != Alerts.end() && i->second) {
			i->second->closeBox();
		}
	} else if (name == u"send_message"_q) {
		SendFromPlugin(data);
	} else if (name == u"copy"_q) {
		QGuiApplication::clipboard()->setText(data[u"text"_q].toString());
	} else if (name == u"open_url"_q) {
		UrlClickHandler::Open(data[u"url"_q].toString());
	}
}

[[nodiscard]] QByteArray HostCall(
		const QByteArray &nameBytes,
		const QByteArray &payload) {
	const auto name = QString::fromUtf8(nameBytes);
	const auto data = QJsonDocument::fromJson(payload).object();
	if (name == u"log"_q) {
		AddLog(data[u"text"_q].toString());
	} else if (name == u"user_id"_q) {
		return QByteArray::number(qlonglong(SelfId.load()));
	} else {
		crl::on_main([=] { HandleOnMain(name, data); });
	}
	return QByteArray("null");
}

} // namespace

bool RussianInterface() {
	return Lang::Id().startsWith(u"ru"_q);
}

QString Phrase(const QString &en, const QString &ru) {
	return RussianInterface() ? ru : en;
}

QString PluginsFolder() {
	return cWorkingDir() + u"extera/plugins"_q;
}

void StartPlugins() {
	const auto runtime = cExeDir() + u"python"_q;
	const auto sdk = cExeDir() + u"extera/sdk"_q;
	if (!Python::Start(runtime, sdk, HostCall)) {
		AddLog(Python::Error());
		return;
	}
	if (const auto session = Core::App().maybePrimarySession()) {
		SelfId = qint64(session->userId().bare);
	}
	PluginsRequest(u"start"_q, QJsonObject{
		{ u"plugins_dir"_q, PluginsFolder() },
		{ u"data_dir"_q, cWorkingDir() + u"extera/data"_q },
		{ u"ru"_q, RussianInterface() },
	});
}

bool PluginsRunning() {
	return Python::Running();
}

QString PluginsError() {
	return Python::Error();
}

QString PluginsLog() {
	QMutexLocker lock(&LogMutex);
	return LogLines.join(QChar('\n'));
}

QJsonValue PluginsRequest(
		const QString &name,
		const QJsonObject &payload,
		QString *error) {
	if (!Python::Running()) {
		return QJsonValue();
	}
	const auto answer = QJsonDocument::fromJson(Python::Call(
		name.toUtf8(),
		QJsonDocument(payload).toJson(QJsonDocument::Compact))).object();
	if (answer[u"ok"_q].toBool()) {
		return answer[u"result"_q];
	}
	const auto text = answer.isEmpty()
		? Python::Error()
		: answer[u"error"_q].toString();
	AddLog(u"%1 failed: %2\n%3"_q.arg(
		name,
		text,
		answer[u"trace"_q].toString()));
	if (error) {
		*error = text;
	}
	return QJsonValue();
}

bool ProcessOutgoing(Api::MessageToSend &message) {
	const auto &text = message.textWithTags.text;
	if (!Python::Running() || SendingFromPlugin || text.isEmpty()) {
		return true;
	}
	const auto peer = message.action.history->peer;
	const auto session = &peer->session();
	LastSession = base::make_weak(session);
	SelfId = qint64(session->userId().bare);

	const auto result = PluginsRequest(u"send_hook"_q, QJsonObject{
		{ u"peer"_q, DialogId(peer) },
		{ u"text"_q, text },
	}).toObject();
	if (result.isEmpty()) {
		return true;
	} else if (result[u"cancel"_q].toBool()) {
		return false;
	}
	const auto changed = result[u"text"_q].toString();
	const auto entities = result[u"entities"_q].toArray();
	if (changed != text || !entities.isEmpty()) {
		message.textWithTags = TextWithTags{
			changed,
			TagsFromJson(entities),
		};
	}
	return true;
}

} // namespace Extera
