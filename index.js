const { Telegraf } = require('telegraf');

const bot = new Telegraf('8669693256:AAHLr95asL_AieENA5eFTcJJIl9ghaIOwzM');

bot.start((ctx) => ctx.reply('Welcome to VedaTrader Bot!'));

bot.launch();