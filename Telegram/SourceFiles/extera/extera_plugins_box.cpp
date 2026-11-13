/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#include "extera/extera_plugins_box.h"

#include "extera/extera_plugins.h"
#include "api/api_common.h"
#include "apiwrap.h"
#include "core/application.h"
#include "core/file_utilities.h"
#include "data/data_document.h"
#include "data/data_file_click_handler.h"
#include "data/data_file_origin.h"
#include "history/history_item.h"
#include "lang/lang_keys.h"
#include "main/main_session.h"
#include "settings/settings_common.h"
#include "storage/localimageloader.h"
#include "storage/storage_media_prepare.h"
#include "ui/abstract_button.h"
#include "ui/boxes/confirm_box.h"
#include "ui/chat/attach/attach_prepare.h"
#include "ui/layers/generic_box.h"
#include "ui/layers/show.h"
#include "ui/painter.h"
#include "ui/qt_object_factory.h"
#include "ui/text/text.h"
#include "ui/text/text_utilities.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/checkbox.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/widgets/labels.h"
#include "ui/widgets/shadow.h"
#include "ui/wrap/padding_wrap.h"
#include "ui/wrap/slide_wrap.h"
#include "ui/wrap/vertical_layout.h"
#include "window/window_controller.h"
#include "window/window_peer_menu.h"
#include "window/window_session_controller.h"
#include "styles/style_boxes.h"
#include "styles/style_extera.h"
#include "styles/style_layers.h"
#include "styles/style_menu_icons.h"
#include "styles/style_settings.h"
#include "styles/style_widgets.h"

#include <QtCore/QJsonArray>
#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>

namespace Extera {
namespace {

struct ListState {
	Fn<void()> rebuild;
	QString query;
};

struct ToggleRowArgs {
	QString title;
	QString about;
	bool checked = false;
	bool accent = false;
};

struct ToggleRowState {
	Ui::Text::String title;
	Ui::Text::String about;
	std::unique_ptr<Ui::ToggleView> toggle;
};

struct Waiting {
	rpl::lifetime lifetime;
	bool done = false;
};

[[nodiscard]] QString StatusText(const QJsonObject &plugin) {
	const auto status = plugin[u"status"_q].toString();
	if (!plugin[u"error"_q].toString().isEmpty()) {
		return Phrase(u"Error"_q, u"Ошибка"_q);
	} else if (status == u"works"_q) {
		return Phrase(u"Works"_q, u"Работает"_q);
	} else if (status == u"partial"_q) {
		return Phrase(u"Partially"_q, u"Частично"_q);
	} else if (status == u"phone"_q) {
		return Phrase(u"Not for PC"_q, u"Не для ПК"_q);
	}
	return Phrase(u"Doesn't work"_q, u"Не работает"_q);
}

not_null<Ui::SettingsButton*> AddPlainButton(
		not_null<Ui::VerticalLayout*> container,
		const QString &text,
		const style::SettingsButton &st = st::settingsButtonNoIcon) {
	return container->add(object_ptr<Ui::SettingsButton>(
		container,
		rpl::single(text),
		st));
}

void ChooseBox(
		not_null<Ui::GenericBox*> box,
		QString title,
		QJsonArray items,
		int current,
		Fn<void(int)> done) {
	box->setTitle(title);

	const auto container = box->verticalLayout();
	auto index = 0;
	for (const auto &item : items) {
		const auto mark = (index == current) ? u"✓ "_q : QString();
		AddPlainButton(
			container,
			mark + item.toString()
		)->setClickedCallback([=] {
			done(index);
			box->closeBox();
		});
		++index;
	}
	box->addButton(tr::lng_cancel(), [=] { box->closeBox(); });
}

void InputBox(
		not_null<Ui::GenericBox*> box,
		QString title,
		QString value,
		Fn<void(QString)> done) {
	box->setTitle(title);

	const auto field = box->addRow(object_ptr<Ui::InputField>(
		box,
		st::defaultInputField,
		rpl::single(title),
		value));
	box->setFocusCallback([=] { field->setFocusFast(); });

	const auto save = [=] {
		done(field->getLastText());
		box->closeBox();
	};
	field->submits(
	) | rpl::on_next([=] {
		save();
	}, field->lifetime());
	box->addButton(tr::lng_settings_save(), save);
	box->addButton(tr::lng_cancel(), [=] { box->closeBox(); });
}

void AddSettings(
		not_null<Ui::VerticalLayout*> list,
		std::shared_ptr<Ui::Show> show,
		const QString &id,
		Fn<void()> refresh) {
	const auto rows = PluginsRequest(
		u"settings"_q,
		QJsonObject{ { u"id"_q, id } }).toArray();
	for (const auto &rowValue : rows) {
		const auto row = rowValue.toObject();
		const auto type = row[u"type"_q].toString();
		const auto text = row[u"text"_q].toString();
		const auto subtext = row[u"subtext"_q].toString();
		const auto key = row[u"key"_q].toString();
		const auto set = [=](QJsonValue value) {
			PluginsRequest(u"set_setting"_q, QJsonObject{
				{ u"id"_q, id },
				{ u"key"_q, key },
				{ u"value"_q, value },
			});
		};
		if (type == u"header"_q) {
			Ui::AddSkip(list);
			Ui::AddSubsectionTitle(list, rpl::single(text));
		} else if (type == u"divider"_q) {
			Ui::AddSkip(list);
			if (text.isEmpty()) {
				Ui::AddDivider(list);
			} else {
				Ui::AddDividerText(list, rpl::single(text));
			}
			Ui::AddSkip(list);
		} else if (type == u"switch"_q) {
			const auto button = AddPlainButton(list, text)->toggleOn(
				rpl::single(row[u"value"_q].toBool()));
			button->toggledChanges(
			) | rpl::on_next([=](bool toggled) {
				set(toggled);
			}, button->lifetime());
		} else if (type == u"selector"_q) {
			const auto items = row[u"items"_q].toArray();
			const auto current = row[u"value"_q].toInt();
			const auto button = Settings::AddButtonWithLabel(
				list,
				rpl::single(text),
				rpl::single(items.at(current).toString()),
				st::settingsButtonNoIcon);
			button->setClickedCallback([=] {
				show->showBox(Box(ChooseBox, text, items, current, [=](
						int index) {
					set(index);
					refresh();
				}));
			});
		} else if (type == u"input"_q || type == u"edit_text"_q) {
			const auto current = row[u"value"_q].toVariant().toString();
			const auto button = Settings::AddButtonWithLabel(
				list,
				rpl::single(text),
				rpl::single(current),
				st::settingsButtonNoIcon);
			button->setClickedCallback([=] {
				show->showBox(Box(InputBox, text, current, [=](
						QString value) {
					set(value);
					refresh();
				}));
			});
		} else if (type == u"text"_q) {
			const auto button = AddPlainButton(list, text);
			if (row[u"clickable"_q].toBool()) {
				const auto index = row[u"index"_q].toInt();
				button->setClickedCallback([=] {
					PluginsRequest(u"setting_click"_q, QJsonObject{
						{ u"id"_q, id },
						{ u"index"_q, index },
					});
				});
			}
		}
		if (!subtext.isEmpty() && type != u"divider"_q) {
			Ui::AddDividerText(list, rpl::single(subtext));
		}
	}
}

[[nodiscard]] bool Matches(const QJsonObject &plugin, const QString &query) {
	if (query.isEmpty()) {
		return true;
	}
	for (const auto &key : { u"name"_q, u"description"_q, u"author"_q }) {
		if (plugin[key].toString().contains(query, Qt::CaseInsensitive)) {
			return true;
		}
	}
	return false;
}

not_null<Ui::VerticalLayout*> AddCard(
		not_null<Ui::VerticalLayout*> container) {
	const auto card = container->add(
		object_ptr<Ui::VerticalLayout>(container),
		st::exteraCardMargin);
	card->paintRequest(
	) | rpl::on_next([=] {
		auto p = QPainter(card);
		auto hq = PainterHighQualityEnabler(p);
		p.setPen(Qt::NoPen);
		p.setBrush(st::exteraCardBg);
		p.drawRoundedRect(
			card->rect(),
			st::exteraCardRadius,
			st::exteraCardRadius);
	}, card->lifetime());
	return card;
}

not_null<Ui::AbstractButton*> AddToggleRow(
		not_null<Ui::VerticalLayout*> container,
		ToggleRowArgs &&args,
		Fn<void(bool)> changed,
		const style::margins &margin = style::margins()) {
	const auto row = container->add(
		object_ptr<Ui::AbstractButton>(container),
		margin);
	const auto accent = args.accent;
	const auto single = args.about.isEmpty();
	row->resize(
		row->width(),
		(single
			? st::exteraToggleRowSingleHeight
			: st::exteraToggleRowHeight));

	const auto state = row->lifetime().make_state<ToggleRowState>();
	state->title = Ui::Text::String(st::exteraToggleRowTitle, args.title);
	state->about = Ui::Text::String(st::exteraToggleRowAbout, args.about);
	state->toggle = std::make_unique<Ui::ToggleView>(
		((accent && args.checked) ? st::exteraToggleActive : st::exteraToggle),
		args.checked,
		[=] { row->update(); });

	row->paintRequest(
	) | rpl::on_next([=] {
		auto p = Painter(row);
		const auto &padding = st::exteraToggleRowPadding;
		const auto active = accent && state->toggle->checked();
		if (accent) {
			auto hq = PainterHighQualityEnabler(p);
			p.setPen(Qt::NoPen);
			p.setBrush(active ? st::windowBgActive : st::exteraCardBg);
			p.drawRoundedRect(
				row->rect(),
				st::exteraCardRadius,
				st::exteraCardRadius);
		}
		const auto size = state->toggle->getSize();
		const auto toggleLeft = row->width()
			- padding.right()
			- size.width();
		const auto available = toggleLeft
			- st::exteraToggleRowSkip
			- padding.left();
		if (available > 0) {
			const auto titleHeight = st::exteraToggleRowTitle.font->height;
			p.setPen(active ? st::windowFgActive : st::windowBoldFg);
			state->title.drawLeftElided(
				p,
				padding.left(),
				single ? ((row->height() - titleHeight) / 2) : padding.top(),
				available,
				row->width());
			if (!single) {
				p.setPen(st::windowSubTextFg);
				state->about.drawLeftElided(
					p,
					padding.left(),
					padding.top() + st::exteraToggleRowAboutTop,
					available,
					row->width());
			}
		}
		state->toggle->paint(
			p,
			toggleLeft,
			(row->height() - size.height()) / 2,
			row->width());
	}, row->lifetime());

	row->setClickedCallback([=] {
		const auto checked = !state->toggle->checked();
		if (accent) {
			state->toggle->setStyle(checked
				? st::exteraToggleActive
				: st::exteraToggle);
		}
		state->toggle->setChecked(checked, anim::type::normal);
		changed(checked);
	});
	return row;
}

void SharePlugin(const QString &path) {
	const auto window = Core::App().activeWindow();
	const auto controller = window ? window->sessionController() : nullptr;
	if (!controller) {
		return;
	}
	const auto session = &controller->session();
	Window::ShowChooseRecipientBox(controller, [=](
			not_null<Data::Thread*> thread) {
		auto list = Storage::PrepareMediaList(
			QStringList{ path },
			st::sendMediaPreviewSize,
			session->premium());
		if (list.error != Ui::PreparedList::Error::None) {
			return false;
		}
		session->api().sendFiles(
			std::move(list),
			SendMediaType::File,
			nullptr,
			Api::SendAction(thread));
		return true;
	});
}

void PluginSettingsBox(
		not_null<Ui::GenericBox*> box,
		QString id,
		QString name) {
	box->setStyle(st::layerBox);
	box->setTitle(name);
	box->setWidth(st::boxWideWidth);

	const auto container = box->verticalLayout();
	const auto list = container->add(
		object_ptr<Ui::VerticalLayout>(container));
	const auto show = box->uiShow();
	const auto state = list->lifetime().make_state<ListState>();
	const auto refresh = [=] {
		crl::on_main(list, [=] { state->rebuild(); });
	};
	state->rebuild = [=] {
		list->clear();
		AddSettings(list, show, id, refresh);
		if (!list->count()) {
			Ui::AddDividerText(list, rpl::single(Phrase(
				u"This plugin has no settings."_q,
				u"У этого плагина нет настроек."_q)));
		}
		if (const auto width = container->width()) {
			list->resizeToWidth(width);
		}
	};
	state->rebuild();

	box->addButton(tr::lng_close(), [=] { box->closeBox(); });
}

void AddPluginButtons(
		not_null<Ui::VerticalLayout*> card,
		std::shared_ptr<Ui::Show> show,
		const QJsonObject &plugin,
		Fn<void()> refresh) {
	const auto id = plugin[u"id"_q].toString();
	const auto name = plugin[u"name"_q].toString();
	const auto path = plugin[u"path"_q].toString();
	const auto pinned = plugin[u"pinned"_q].toBool();
	const auto row = card->add(object_ptr<Ui::FixedHeightWidget>(
		card,
		st::exteraPluginButtonsHeight));
	auto left = st::exteraPluginButtonsSkip;
	const auto add = [&](const style::IconButton &look, Fn<void()> callback) {
		const auto button = Ui::CreateChild<Ui::IconButton>(row, look);
		button->setClickedCallback(std::move(callback));
		button->move(left, 0);
		button->show();
		left += button->width();
	};
	add(st::exteraPluginShare, [=] {
		SharePlugin(path);
	});
	add(st::exteraPluginOpen, [=] {
		File::OpenWith(path, [=] { File::ShowInFolder(path); });
	});
	add(pinned ? st::exteraPluginUnpin : st::exteraPluginPin, [=] {
		PluginsRequest(u"set_pinned"_q, QJsonObject{
			{ u"id"_q, id },
			{ u"pinned"_q, !pinned },
		});
		refresh();
	});
	if (plugin[u"has_settings"_q].toBool()) {
		add(st::exteraPluginSettings, [=] {
			show->showBox(Box(PluginSettingsBox, id, name));
		});
	}

	const auto remove = Ui::CreateChild<Ui::IconButton>(
		row,
		st::exteraPluginDelete);
	remove->show();
	remove->setClickedCallback([=] {
		auto text = TextWithEntities{ Phrase(
			u"Are you sure you want to delete "_q,
			u"Вы уверены, что хотите удалить "_q) };
		text.append(Ui::Text::Bold(name)).append(u"?"_q);
		show->showBox(Ui::MakeConfirmBox({
			.text = std::move(text),
			.confirmed = [=](Fn<void()> close) {
				PluginsRequest(u"delete"_q, QJsonObject{ { u"id"_q, id } });
				refresh();
				close();
			},
			.confirmText = tr::lng_box_delete(),
			.confirmStyle = &st::attentionBoxButton,
			.title = Phrase(u"Delete plugin"_q, u"Удалить плагин"_q),
		}));
	});
	row->widthValue(
	) | rpl::on_next([=](int width) {
		remove->move(
			width - st::exteraPluginButtonsSkip - remove->width(),
			0);
	}, remove->lifetime());
}

void AddPluginCard(
		not_null<Ui::VerticalLayout*> list,
		std::shared_ptr<Ui::Show> show,
		const QJsonObject &plugin,
		Fn<void()> refresh) {
	const auto id = plugin[u"id"_q].toString();
	const auto author = plugin[u"author"_q].toString();
	const auto about = plugin[u"description"_q].toString();
	const auto error = plugin[u"error"_q].toString();
	const auto card = AddCard(list);

	AddToggleRow(card, {
		.title = plugin[u"name"_q].toString(),
		.about = (u"v"_q
			+ plugin[u"version"_q].toString()
			+ (author.isEmpty() ? QString() : (u" • "_q + author))),
		.checked = plugin[u"enabled"_q].toBool(),
	}, [=](bool enabled) {
		auto failed = QString();
		const auto info = PluginsRequest(u"set_enabled"_q, QJsonObject{
			{ u"id"_q, id },
			{ u"enabled"_q, enabled },
		}, &failed).toObject();
		const auto problem = failed.isEmpty()
			? info[u"error"_q].toString()
			: failed;
		if (!problem.isEmpty()) {
			show->showToast(problem);
		}
		refresh();
	});
	if (!about.isEmpty()) {
		card->add(
			object_ptr<Ui::FlatLabel>(card, about, st::exteraPluginAbout),
			st::exteraPluginAboutMargin);
	}
	if (!error.isEmpty()) {
		card->add(
			object_ptr<Ui::FlatLabel>(
				card,
				Phrase(u"Did not start: "_q, u"Не запустился: "_q) + error,
				st::exteraPluginError),
			st::exteraPluginAboutMargin);
	}
	card->add(object_ptr<Ui::PlainShadow>(card), st::exteraCardLineMargin);
	AddPluginButtons(card, show, plugin, refresh);
}

void InstallBox(
		not_null<Ui::GenericBox*> box,
		QString path,
		Fn<void()> done) {
	box->setStyle(st::layerBox);
	box->setWidth(st::boxWideWidth);

	auto failed = PluginsRunning() ? QString() : PluginsError();
	const auto info = PluginsRequest(
		u"inspect"_q,
		QJsonObject{ { u"path"_q, path } },
		&failed).toObject();
	if (info.isEmpty()) {
		box->setTitle(Phrase(u"Plugin"_q, u"Плагин"_q));
		box->addRow(object_ptr<Ui::FlatLabel>(
			box,
			Phrase(
				u"This file cannot be installed: "_q,
				u"Этот файл нельзя установить: "_q) + failed,
			st::boxLabel));
		box->addButton(tr::lng_close(), [=] { box->closeBox(); });
		return;
	}

	const auto container = box->verticalLayout();
	const auto show = box->uiShow();
	const auto update = info[u"installed"_q].toBool();
	const auto status = info[u"status"_q].toString();
	const auto usable = (status == u"works"_q) || (status == u"partial"_q);
	const auto author = info[u"author"_q].toString();
	const auto about = info[u"description"_q].toString();
	const auto reason = info[u"reason"_q].toString();

	const auto icon = container->add(
		object_ptr<Ui::FixedHeightWidget>(
			container,
			st::exteraInstallIconSize),
		st::exteraInstallIconMargin);
	icon->paintRequest(
	) | rpl::on_next([=] {
		auto p = QPainter(icon);
		auto hq = PainterHighQualityEnabler(p);
		const auto size = st::exteraInstallIconSize;
		const auto rect = QRect((icon->width() - size) / 2, 0, size, size);
		p.setPen(Qt::NoPen);
		p.setBrush(st::windowBgActive);
		p.drawEllipse(rect);
		st::exteraInstallIcon.paintInCenter(p, rect);
	}, icon->lifetime());

	container->add(
		object_ptr<Ui::FlatLabel>(
			container,
			info[u"name"_q].toString(),
			st::exteraInstallName),
		st::exteraInstallNameMargin,
		style::al_top);

	auto line = TextWithEntities{ Phrase(u"Version "_q, u"Версия "_q) };
	if (update) {
		line.append(
			Ui::Text::StrikeOut(info[u"old_version"_q].toString())
		).append(u" → "_q);
	}
	line.append(info[u"version"_q].toString());
	if (!author.isEmpty()) {
		line.append(u" • "_q + author);
	}
	container->add(
		object_ptr<Ui::FlatLabel>(
			container,
			rpl::single(std::move(line)),
			st::exteraInstallVersion),
		st::exteraInstallVersionMargin,
		style::al_top);

	if (!about.isEmpty()) {
		const auto card = AddCard(container);
		card->add(
			object_ptr<Ui::FlatLabel>(card, about, st::exteraPluginAbout),
			st::exteraInstallTextMargin);
	}

	const auto card = AddCard(container);
	card->add(
		object_ptr<Ui::FlatLabel>(
			card,
			StatusText(info),
			st::exteraInstallStatus),
		(reason.isEmpty()
			? st::exteraInstallTextMargin
			: st::exteraInstallStatusMargin));
	if (!reason.isEmpty()) {
		card->add(
			object_ptr<Ui::FlatLabel>(card, reason, st::exteraPluginNote),
			st::exteraInstallReasonMargin);
	}

	const auto enable = (!update && usable)
		? container->add(
			object_ptr<Ui::Checkbox>(
				container,
				Phrase(
					u"Enable after installation"_q,
					u"Включить после установки"_q),
				false,
				st::defaultBoxCheckbox),
			st::exteraInstallCheckMargin)
		: nullptr;

	box->addTopButton(st::exteraBoxOpen, [=] {
		File::OpenWith(path, [=] { File::ShowInFolder(path); });
	});
	box->addButton(rpl::single(update
		? Phrase(u"Update"_q, u"Обновить"_q)
		: Phrase(u"Install"_q, u"Установить"_q)), [=] {
		auto error = QString();
		auto payload = QJsonObject{ { u"path"_q, path } };
		if (enable) {
			payload.insert(u"enable"_q, enable->checked());
		}
		const auto result = PluginsRequest(
			u"install"_q,
			payload,
			&error).toObject();
		show->showToast(result.isEmpty()
			? error
			: ((update
				? Phrase(u"Updated: "_q, u"Обновлён: "_q)
				: Phrase(u"Installed: "_q, u"Установлен: "_q))
				+ result[u"name"_q].toString()));
		if (done) {
			done();
		}
		box->closeBox();
	});
	box->addButton(tr::lng_cancel(), [=] { box->closeBox(); });
}

void SystemBox(not_null<Ui::GenericBox*> box, Fn<void()> changed) {
	box->setStyle(st::layerBox);
	box->setTitle(Phrase(u"Plugin system"_q, u"Система плагинов"_q));
	box->setWidth(st::boxWideWidth);

	const auto container = box->verticalLayout();
	const auto show = box->uiShow();

	Ui::AddSkip(container);
	Ui::AddSubsectionTitle(container, rpl::single(Phrase(
		u"Settings"_q,
		u"Настройки"_q)));
	const auto confirm = Settings::AddButtonWithIcon(
		container,
		rpl::single(Phrase(
			u"Confirm important actions"_q,
			u"Подтверждать важные действия"_q)),
		st::settingsButton,
		{ &st::menuIconPermissions }
	)->toggleOn(rpl::single(PluginsOption(u"confirm_sensitive"_q)));
	confirm->toggledChanges(
	) | rpl::on_next([=](bool value) {
		SetPluginsOption(u"confirm_sensitive"_q, value);
	}, confirm->lifetime());
	Ui::AddSkip(container);
	Ui::AddDividerText(container, rpl::single(Phrase(
		u"Plugins will not be able to spend stars, transfer gifts or "
		u"change account security without your confirmation."_q,
		u"Плагины не смогут тратить звёзды, передавать подарки и менять "
		u"безопасность аккаунта без вашего подтверждения."_q)));

	Ui::AddSkip(container);
	const auto safe = Settings::AddButtonWithIcon(
		container,
		rpl::single(Phrase(u"Safe mode"_q, u"Безопасный режим"_q)),
		st::settingsButton,
		{ &st::menuIconLock }
	)->toggleOn(rpl::single(PluginsOption(u"safe_mode"_q)));
	safe->toggledChanges(
	) | rpl::on_next([=](bool value) {
		SetPluginsOption(u"safe_mode"_q, value);
		changed();
	}, safe->lifetime());
	Ui::AddSkip(container);
	Ui::AddDividerText(container, rpl::single(Phrase(
		u"In safe mode all plugins are inactive. This lets you safely "
		u"find and disable a problematic plugin."_q,
		u"В безопасном режиме все плагины неактивны. Это позволяет "
		u"безопасно найти и отключить проблемный плагин."_q)));

	Ui::AddSkip(container);
	Ui::AddSubsectionTitle(container, rpl::single(u"Python SDK"_q));
	Settings::AddButtonWithLabel(
		container,
		rpl::single(Phrase(u"Version"_q, u"Версия"_q)),
		rpl::single(
			PluginsRequest(u"about"_q).toObject()[u"sdk"_q].toString()),
		st::settingsButtonNoIcon);

	Ui::AddSkip(container);
	Ui::AddDivider(container);
	Ui::AddSkip(container);
	Ui::AddSubsectionTitle(container, rpl::single(Phrase(
		u"Files"_q,
		u"Файлы"_q)));
	AddPlainButton(
		container,
		Phrase(u"Install from file"_q, u"Установить из файла"_q)
	)->setClickedCallback([=] {
		FileDialog::GetOpenPath(
			box.get(),
			Phrase(u"Choose a plugin"_q, u"Выберите плагин"_q),
			u"Plugins (*.plugin *.py);;All files (*.*)"_q,
			crl::guard(box.get(), [=](FileDialog::OpenResult &&result) {
				if (!result.paths.isEmpty()) {
					ShowInstallPlugin(show, result.paths.front(), changed);
				}
			}));
	});
	AddPlainButton(
		container,
		Phrase(u"Open plugins folder"_q, u"Открыть папку плагинов"_q)
	)->setClickedCallback([=] {
		File::Launch(PluginsFolder());
	});
	AddPlainButton(
		container,
		Phrase(u"Copy plugin log"_q, u"Скопировать журнал плагинов"_q)
	)->setClickedCallback([=] {
		QGuiApplication::clipboard()->setText(PluginsLog());
		show->showToast(Phrase(u"Copied."_q, u"Скопировано."_q));
	});
	Ui::AddSkip(container);

	box->addButton(tr::lng_close(), [=] { box->closeBox(); });
}

} // namespace

void PluginsBox(not_null<Ui::GenericBox*> box) {
	box->setStyle(st::layerBox);
	box->setTitle(Phrase(u"Plugins"_q, u"Плагины"_q));
	box->setWidth(st::boxWideWidth);

	const auto container = box->verticalLayout();
	const auto search = container->add(
		object_ptr<Ui::SlideWrap<Ui::InputField>>(
			container,
			object_ptr<Ui::InputField>(
				container,
				st::defaultInputField,
				rpl::single(Phrase(u"Search"_q, u"Поиск"_q))),
			st::exteraSearchMargin));
	search->hide(anim::type::instant);
	const auto field = search->entity();
	const auto list = container->add(
		object_ptr<Ui::VerticalLayout>(container));
	const auto show = box->uiShow();
	const auto state = list->lifetime().make_state<ListState>();
	const auto refresh = [=] {
		crl::on_main(list, [=] { state->rebuild(); });
	};
	state->rebuild = [=] {
		list->clear();
		const auto finish = [=] {
			if (const auto width = container->width()) {
				list->resizeToWidth(width);
			}
		};
		if (!PluginsRunning()) {
			Ui::AddDividerText(list, rpl::single(Phrase(
				u"The plugin engine did not start: "_q,
				u"Движок плагинов не запустился: "_q)
				+ PluginsError()));
			finish();
			return;
		}

		Ui::AddSkip(list, st::exteraListSkip);
		AddToggleRow(list, {
			.title = Phrase(
				u"Enable plugin system"_q,
				u"Включить систему плагинов"_q),
			.checked = PluginsOption(u"engine"_q),
			.accent = true,
		}, [=](bool enabled) {
			SetPluginsOption(u"engine"_q, enabled);
			refresh();
		}, st::exteraCardMargin);

		for (const auto &value : PluginsRequest(u"list"_q).toArray()) {
			const auto plugin = value.toObject();
			if (Matches(plugin, state->query)) {
				AddPluginCard(list, show, plugin, refresh);
			}
		}

		const auto actions = PluginsRequest(
			u"menu"_q,
			QJsonObject{ { u"location"_q, u"main_menu"_q } }).toArray();
		if (!actions.isEmpty()) {
			Ui::AddSubsectionTitle(list, rpl::single(Phrase(
				u"Plugin actions"_q,
				u"Действия плагинов"_q)));
			for (const auto &value : actions) {
				const auto action = value.toObject();
				const auto actionId = action[u"id"_q];
				AddPlainButton(
					list,
					action[u"text"_q].toString()
				)->setClickedCallback([=] {
					PluginsRequest(
						u"menu_click"_q,
						QJsonObject{ { u"id"_q, actionId } });
				});
			}
			Ui::AddSkip(list);
		}

		finish();
	};
	state->rebuild();

	field->changes(
	) | rpl::on_next([=] {
		state->query = field->getLastText().trimmed();
		state->rebuild();
	}, field->lifetime());

	box->addTopButton(st::exteraBoxInfo, [=] {
		show->showBox(Box(SystemBox, refresh));
	});
	box->addTopButton(st::exteraBoxSearch, [=] {
		const auto shown = !search->toggled();
		search->toggle(shown, anim::type::normal);
		if (shown) {
			field->setFocusFast();
		} else if (!field->getLastText().isEmpty()) {
			field->clear();
			state->query = QString();
			state->rebuild();
		}
	});
	box->addButton(tr::lng_close(), [=] { box->closeBox(); });
}

void ShowInstallPlugin(
		std::shared_ptr<Ui::Show> show,
		const QString &path,
		Fn<void()> done) {
	show->showBox(Box(InstallBox, path, std::move(done)));
}

bool OpenPluginDocument(
		not_null<Window::SessionController*> controller,
		not_null<DocumentData*> document,
		HistoryItem *item) {
	if (!document->filename().endsWith(u".plugin"_q, Qt::CaseInsensitive)) {
		return false;
	}
	document->saveFromDataSilent();
	const auto path = document->filepath(true);
	if (!path.isEmpty()) {
		ShowInstallPlugin(controller->window().uiShow(), path);
		return true;
	}
	if (document->status == FileReady
		|| document->status == FileDownloadFailed) {
		DocumentSaveClickHandler::Save(
			item ? item->fullId() : Data::FileOrigin(),
			document);
	}
	const auto state = controller->lifetime().make_state<Waiting>();
	document->session().downloaderTaskFinished(
	) | rpl::on_next([=] {
		if (state->done) {
			return;
		}
		const auto ready = document->filepath(true);
		if (ready.isEmpty() && document->loading()) {
			return;
		}
		state->done = true;
		crl::on_main(controller.get(), [=] {
			state->lifetime.destroy();
			if (!ready.isEmpty()) {
				ShowInstallPlugin(controller->window().uiShow(), ready);
			}
		});
	}, state->lifetime);
	return true;
}

} // namespace Extera
