/*
This file is part of extera Desktop,
an unofficial exteraGram build for PC based on Telegram Desktop.

For license and copyright information please follow this link:
https://github.com/tnt-cat/exera-desktop/blob/exg/LEGAL
*/
#include "extera/extera_plugins_box.h"

#include "extera/extera_plugins.h"
#include "core/file_utilities.h"
#include "lang/lang_keys.h"
#include "settings/settings_common.h"
#include "ui/layers/generic_box.h"
#include "ui/layers/show.h"
#include "ui/vertical_list.h"
#include "ui/widgets/buttons.h"
#include "ui/widgets/fields/input_field.h"
#include "ui/wrap/vertical_layout.h"
#include "styles/style_layers.h"
#include "styles/style_settings.h"
#include "styles/style_widgets.h"

#include <QtCore/QJsonArray>
#include <QtGui/QClipboard>
#include <QtGui/QGuiApplication>

namespace Extera {
namespace {

struct Rebuilder {
	Fn<void()> rebuild;
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

[[nodiscard]] QString AboutText(const QJsonObject &plugin) {
	auto lines = QStringList();
	const auto add = [&](const QString &line) {
		if (!line.isEmpty()) {
			lines.push_back(line);
		}
	};
	const auto author = plugin[u"author"_q].toString();
	const auto reason = plugin[u"reason"_q].toString();
	const auto error = plugin[u"error"_q].toString();
	auto unsupported = QStringList();
	for (const auto &value : plugin[u"unsupported"_q].toArray()) {
		unsupported.push_back(value.toString());
	}

	add(Phrase(u"Version "_q, u"Версия "_q)
		+ plugin[u"version"_q].toString()
		+ (author.isEmpty() ? QString() : (u" · "_q + author)));
	add(plugin[u"description"_q].toString());
	add(Phrase(u"Status: "_q, u"Статус: "_q)
		+ StatusText(plugin)
		+ (reason.isEmpty() ? QString() : (u" — "_q + reason)));
	if (!error.isEmpty()) {
		add(Phrase(u"Did not start: "_q, u"Не запустился: "_q) + error);
	}
	if (!unsupported.isEmpty()) {
		add(Phrase(u"Not available on PC: "_q, u"Недоступно на ПК: "_q)
			+ unsupported.join(u", "_q));
	}
	return lines.join(QChar('\n'));
}

[[nodiscard]] QJsonObject FindPlugin(const QString &id) {
	for (const auto &value : PluginsRequest(u"list"_q).toArray()) {
		const auto plugin = value.toObject();
		if (plugin[u"id"_q].toString() == id) {
			return plugin;
		}
	}
	return QJsonObject();
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

void PluginBox(
		not_null<Ui::GenericBox*> box,
		QString id,
		Fn<void()> changed) {
	box->setStyle(st::layerBox);
	box->setWidth(st::boxWideWidth);

	const auto container = box->verticalLayout();
	const auto list = container->add(
		object_ptr<Ui::VerticalLayout>(container));
	const auto show = box->uiShow();
	const auto state = list->lifetime().make_state<Rebuilder>();
	const auto refresh = [=] {
		crl::on_main(list, [=] { state->rebuild(); });
	};
	state->rebuild = [=] {
		const auto plugin = FindPlugin(id);
		if (plugin.isEmpty()) {
			box->closeBox();
			return;
		}
		list->clear();
		box->setTitle(plugin[u"name"_q].toString());

		const auto toggle = AddPlainButton(
			list,
			Phrase(u"Enabled"_q, u"Включён"_q)
		)->toggleOn(rpl::single(plugin[u"enabled"_q].toBool()));
		toggle->toggledChanges(
		) | rpl::on_next([=](bool enabled) {
			const auto info = PluginsRequest(u"set_enabled"_q, QJsonObject{
				{ u"id"_q, id },
				{ u"enabled"_q, enabled },
			}).toObject();
			const auto error = info[u"error"_q].toString();
			if (!error.isEmpty()) {
				show->showToast(error);
			}
			changed();
			refresh();
		}, toggle->lifetime());
		Ui::AddSkip(list);
		Ui::AddDividerText(list, rpl::single(AboutText(plugin)));

		if (plugin[u"loaded"_q].toBool()) {
			AddSettings(list, show, id, refresh);
		}

		Ui::AddSkip(list);
		AddPlainButton(
			list,
			Phrase(u"Delete plugin"_q, u"Удалить плагин"_q),
			st::settingsAttentionButton
		)->setClickedCallback([=] {
			PluginsRequest(u"delete"_q, QJsonObject{ { u"id"_q, id } });
			changed();
			box->closeBox();
		});
		Ui::AddSkip(list);

		if (const auto width = container->width()) {
			list->resizeToWidth(width);
		}
	};
	state->rebuild();

	box->addButton(tr::lng_close(), [=] { box->closeBox(); });
}

} // namespace

void PluginsBox(not_null<Ui::GenericBox*> box) {
	box->setStyle(st::layerBox);
	box->setTitle(Phrase(u"Plugins"_q, u"Плагины"_q));
	box->setWidth(st::boxWideWidth);

	const auto container = box->verticalLayout();
	const auto list = container->add(
		object_ptr<Ui::VerticalLayout>(container));
	const auto show = box->uiShow();
	const auto state = list->lifetime().make_state<Rebuilder>();
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

		const auto plugins = PluginsRequest(u"list"_q).toArray();
		Ui::AddSkip(list);
		Ui::AddSubsectionTitle(list, rpl::single(Phrase(
			u"Installed: %1"_q,
			u"Установлено: %1"_q).arg(plugins.size())));
		for (const auto &value : plugins) {
			const auto plugin = value.toObject();
			const auto id = plugin[u"id"_q].toString();
			const auto status = StatusText(plugin)
				+ (plugin[u"enabled"_q].toBool()
					? QString()
					: Phrase(u", off"_q, u", выкл."_q));
			Settings::AddButtonWithLabel(
				list,
				rpl::single(plugin[u"name"_q].toString()),
				rpl::single(status),
				st::settingsButtonNoIcon
			)->setClickedCallback([=] {
				show->showBox(Box(PluginBox, id, refresh));
			});
		}
		Ui::AddSkip(list);
		Ui::AddDividerText(list, rpl::single(Phrase(
			u"Works — the plugin uses only what extera Desktop "
			u"has. Partially — the parts tied to Android will not "
			u"work. Not for PC — the plugin is about phone features."_q,
			u"Работает — плагину хватает того, что есть в extera "
			u"Desktop. Частично — то, что завязано на Android, "
			u"работать не будет. Не для ПК — плагин про функции "
			u"телефона."_q)));

		const auto actions = PluginsRequest(
			u"menu"_q,
			QJsonObject{ { u"location"_q, u"main_menu"_q } }).toArray();
		if (!actions.isEmpty()) {
			Ui::AddSkip(list);
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
			Ui::AddDivider(list);
		}

		Ui::AddSkip(list);
		AddPlainButton(
			list,
			Phrase(u"Install from file"_q, u"Установить из файла"_q)
		)->setClickedCallback([=] {
			FileDialog::GetOpenPath(
				box.get(),
				Phrase(u"Choose a plugin"_q, u"Выберите плагин"_q),
				u"Plugins (*.plugin *.py);;All files (*.*)"_q,
				crl::guard(list, [=](FileDialog::OpenResult &&result) {
					if (result.paths.isEmpty()) {
						return;
					}
					auto error = QString();
					const auto info = PluginsRequest(
						u"install"_q,
						QJsonObject{ { u"path"_q, result.paths.front() } },
						&error).toObject();
					show->showToast(info.isEmpty()
						? error
						: (Phrase(u"Installed: "_q, u"Установлен: "_q)
							+ info[u"name"_q].toString()));
					refresh();
				}));
		});
		AddPlainButton(
			list,
			Phrase(
				u"Open plugins folder"_q,
				u"Открыть папку плагинов"_q)
		)->setClickedCallback([=] {
			File::Launch(PluginsFolder());
		});
		AddPlainButton(
			list,
			Phrase(
				u"Copy plugin log"_q,
				u"Скопировать журнал плагинов"_q)
		)->setClickedCallback([=] {
			QGuiApplication::clipboard()->setText(PluginsLog());
			show->showToast(Phrase(u"Copied."_q, u"Скопировано."_q));
		});
		Ui::AddSkip(list);

		finish();
	};
	state->rebuild();

	box->addButton(tr::lng_close(), [=] { box->closeBox(); });
}

} // namespace Extera
