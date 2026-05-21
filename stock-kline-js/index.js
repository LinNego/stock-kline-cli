#!/usr/bin/env node

const axios = require('axios');
const iconv = require('iconv-lite');
const { table } = require('table');
const fs = require('fs');
const { program } = require('commander');
const asciichart = require('asciichart');
const chalk = require('chalk');

const columns = ['名字', '代码', '当前股价', '今日涨跌幅', '昨日收盘价'];

const config = {
  showHead: true,
  defaultPeriod: 20, // 默认周期数
  enableAIAnalysis: false // 默认不开启AI分析
}

// 股票市场配置
const MARKET_CONFIG = {
  // A股
  sh: { type: 'A', name: '上证', api: 'qt.gtimg.cn', needConvert: true, currency: '￥' },
  sz: { type: 'A', name: '深证', api: 'qt.gtimg.cn', needConvert: true, currency: '￥' },
  // 港股
  hk: { type: 'HK', name: '港股', api: 'qt.gtimg.cn', needConvert: true, currency: 'HK$' },
  // 美股
  us: { type: 'US', name: '美股', api: 'qt.gtimg.cn', needConvert: true, currency: '$' }
};

program
  .version('1.0.4', '-v, --version')
  .option('-c, --config <path>', '设置配置文件')
  .option('-d', '隐藏表头')
  .option('-s, --stock <list>', '设置stock代码, 多个以逗号隔开\n  A股示例: sh600000,sz000001\n  港股示例: hk00700\n  美股示例: usAAPL', (val) => val.split(','))
  .option('--day', '显示日K数据')
  .option('--week', '显示周K数据')
  .option('-p, --period <number>', '设置显示的周期数量，默认20', (val) => parseInt(val))
  .option('--height <number>', '设置图表高度，默认15', (val) => parseInt(val))
  .option('--ai', '开启AI分析')
  .helpOption('--help', '显示帮助信息')

program.parse();

const options = program.opts();
if (options.d) {
  config.showHead = false;
}
if (options.ai) {
  config.enableAIAnalysis = true;
}

if (options.stock) {
  printStock(options.stock)
} else if (options.config) {
  const data = fs.readFileSync(options.config);
  const configData = JSON.parse(data);
  printStock(configData.stocks);
}

// 获取股票市场信息
function getMarketInfo(code) {
  const market = code.substring(0, 2).toLowerCase();
  return MARKET_CONFIG[market] || null;
}

async function getKLineData(code, type = 'day') {
  try {
    const marketInfo = getMarketInfo(code);
    if (!marketInfo) {
      throw new Error(`不支持的股票代码格式: ${code}`);
    }

    if (marketInfo.type === 'US') {
      console.log(chalk.red(`\n美股暂不支持K线图: ${code}`));
      return []
    }

    const klineType = type === 'day' ? 'day' : 'week';
    const period = options.period || config.defaultPeriod;
    
    // 根据不同市场使用不同的API参数
    let apiUrl;
    if (marketInfo.type === 'HK') {
      apiUrl = `https://web.ifzq.gtimg.cn/appstock/app/kline/kline?_var=kline_${klineType}${code}&param=${code},${klineType},,,${period}`;
    } else if (marketInfo.type === 'A') {
      apiUrl = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${code},${klineType},,,${period},qfq`;
    }

    // console.log('正在获取K线数据:', apiUrl);
    const response = await axios({
      method: 'get',
      url: apiUrl,
      headers: {
        'Referer': 'http://web.ifzq.gtimg.cn/',
        'User-Agent': 'Mozilla/5.0'
      }
    });

    let data = response.data;
    
    // 处理港股的数据格式
    if (marketInfo.type === 'HK') {
      if (typeof data === 'string') {
        data = JSON.parse(data.replace(/^[^{]*=/, ''));
      }
    }

    const klineData = [];
    let stockData = data.data[code];

    if (!stockData) {
      console.error(`未能获取到${code}的K线数据`);
      return [];
    }

    // console.log('数据结构:', Object.keys(stockData));
    // console.log('K线类型:', klineType);

    // 不同市场和类型的数据结构不同
    let klines = stockData[klineType] || stockData[`qfq${klineType}`];

    if (!klines) {
      console.error(`未能获取到${code}的${type}K线数据`);
      return [];
    }

    // console.log('K线数据长度:', klines.length);
    // if (klines.length > 0) {
    //   console.log('第一条数据:', klines[0]);
    // }

    klines.forEach(k => {
      klineData.push({
        date: k[0],
        open: parseFloat(k[1]),
        close: parseFloat(k[2]),
        high: parseFloat(k[3]),
        low: parseFloat(k[4]),
        volume: parseFloat(k[5])
      });
    });

    return klineData;
  } catch (error) {
    console.error(`获取K线数据失败: ${error.message}`);
    if (error.response) {
      console.error('响应状态:', error.response.status);
      console.error('响应数据:', error.response.data);
    }
    return [];
  }
}

// 分析K线形态
function analyzeKLinePattern(klineData) {
  if (klineData.length < 3) return [];

  const patterns = [];
  
  // 分析最近三天的K线
  const recent = klineData.slice(-3);
  
  // 判断锤子线
  const last = recent[2];
  const bodyLength = Math.abs(last.close - last.open);
  const shadowLength = last.high - last.low;
  const lowerShadow = Math.min(last.open, last.close) - last.low;
  
  if (lowerShadow > bodyLength * 2 && shadowLength > bodyLength * 3) {
    patterns.push({
      type: '锤子线',
      position: last.date,
      meaning: '可能预示着下跌趋势即将结束，市场可能反转向上'
    });
  }

  // 判断启明星形态
  if (recent.length === 3) {
    const [day1, day2, day3] = recent;
    const day1Body = day1.close - day1.open;
    const day2Body = Math.abs(day2.close - day2.open);
    const day3Body = day3.close - day3.open;
    
    if (day1Body < 0 && // 第一天下跌
        day2Body < Math.abs(day1Body) * 0.3 && // 第二天十字星
        day3Body > 0 && // 第三天上涨
        day2.high < day1.close && // 缺口
        day3.open > day2.high) {
      patterns.push({
        type: '启明星',
        position: day3.date,
        meaning: '强势反转信号，预示着可能开始上涨趋势'
      });
    }
  }

  return patterns;
}

// 分析趋势
function analyzeTrend(klineData) {
  if (klineData.length < 5) return null;

  const prices = klineData.map(k => k.close);
  const ma5 = prices.slice(-5).reduce((a, b) => a + b, 0) / 5;
  const ma10 = klineData.length >= 10 ? 
    prices.slice(-10).reduce((a, b) => a + b, 0) / 10 : null;
  
  const lastPrice = prices[prices.length - 1];
  const startPrice = prices[0];
  const priceChange = ((lastPrice - startPrice) / startPrice * 100).toFixed(2);
  
  let trend = '';
  let strength = '';
  
  // 判断趋势
  if (lastPrice > ma5 && (ma10 === null || ma5 > ma10)) {
    trend = '上涨';
    strength = priceChange > 5 ? '强势' : '弱势';
  } else if (lastPrice < ma5 && (ma10 === null || ma5 < ma10)) {
    trend = '下跌';
    strength = priceChange < -5 ? '强势' : '弱势';
  } else {
    trend = '盘整';
    strength = '震荡';
  }

  return {
    trend,
    strength,
    priceChange: `${priceChange}%`,
    analysis: `${strength}${trend}趋势，区间涨跌幅${priceChange}%，${
      trend === '盘整' ? '建议观望' :
      trend === '上涨' ? (strength === '强势' ? '注意防守' : '可以跟进') :
      strength === '强势' ? '注意止损' : '等待企稳'
    }`
  };
}

function printKLineChart(klineData, type, stockName, code) {
  if (klineData.length === 0) return;

  const prices = klineData.map(item => item.close);
  const highs = klineData.map(item => item.high);
  const lows = klineData.map(item => item.low);
  const dates = klineData.map(item => item.date);

  // 设置图表配置
  const chartConfig = {
    height: options.height || 15,
    colors: [
      asciichart.blue,
      asciichart.green,
      asciichart.red
    ]
  };

  // 创建多线图表
  console.log(chalk.yellow(`\n${stockName}(${code}) ${type}K线图 (${klineData.length}个周期):`));
  console.log(chalk.yellow('价格走势 (蓝色:收盘价 绿色:最高价 红色:最低价)'));
  console.log(asciichart.plot([prices, highs, lows], chartConfig));

  // 显示日期范围
  console.log(chalk.cyan('\n时间范围:'));
  console.log(`${dates[0]} 至 ${dates[dates.length - 1]}`);

  // 显示统计信息
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const avgPrice = prices.reduce((a, b) => a + b, 0) / prices.length;
  const priceChange = ((prices[prices.length - 1] - prices[0]) / prices[0] * 100).toFixed(2);

  console.log(chalk.cyan('\n价格统计:'));
  console.log(chalk.green(`最高: ${maxPrice.toFixed(2)}`));
  console.log(chalk.red(`最低: ${minPrice.toFixed(2)}`));
  console.log(chalk.yellow(`平均: ${avgPrice.toFixed(2)}`));
  console.log(chalk.cyan(`区间涨跌: ${priceChange}%`));

  // 只在启用AI分析时显示分析结果
  if (config.enableAIAnalysis) {
    // 添加AI分析
    console.log(chalk.magenta('\nAI分析:'));
    
    // 分析K线形态
    const patterns = analyzeKLinePattern(klineData);
    if (patterns.length > 0) {
      console.log(chalk.yellow('发现K线形态:'));
      patterns.forEach(p => {
        console.log(`- ${p.type} (${p.position})`);
        console.log(`  ${p.meaning}`);
      });
    }

    // 分析趋势
    const trend = analyzeTrend(klineData);
    if (trend) {
      console.log(chalk.yellow('\n趋势分析:'));
      console.log(`- 当前趋势: ${trend.trend} (${trend.strength})`);
      console.log(`- 分析建议: ${trend.analysis}`);
    }
  }
}

async function printStock(list) {
  try {
    const options = program.opts();
    
    // 按市场分组股票代码
    const stocksByMarket = list.reduce((acc, code) => {
      const marketInfo = getMarketInfo(code);
      if (!marketInfo) {
        console.error(`不支持的股票代码格式: ${code}`);
        return acc;
      }
      if (!acc[marketInfo.type]) {
        acc[marketInfo.type] = [];
      }
      acc[marketInfo.type].push(code);
      return acc;
    }, {});

    let tableData = [];
    if (config.showHead) {
      tableData.push(['名字', '代码', '当前股价', '今日涨跌幅', '昨日收盘价']);
    }

    // 处理每个市场的股票
    for (const [marketType, stocks] of Object.entries(stocksByMarket)) {
      const response = await axios({
        method: 'get',
        url: `https://qt.gtimg.cn/q=${stocks.join(',')}`,
        responseType: "arraybuffer"
      });

      let data;
      if (marketType === 'US') {
        data = iconv.decode(response.data, 'gbk');
      } else {
        data = iconv.decode(response.data, 'gbk');
      }

      let arr = data.split('\n');

      for (let i = 0; i < arr.length - 1; i++) {
        let item = arr[i];
        let match = item.match(/v_(.+)="(.+)"/);
        if (match) {
          let values = match[2].split('~');
          let stockCode = match[1];
          let stockName = values[1];
          let marketInfo = getMarketInfo(stockCode);
          
          // 根据不同市场调整数据位置
          const priceIndex = marketType === 'US' ? 3 : 3;
          const changeIndex = marketType === 'US' ? 32 : 32;
          const prevCloseIndex = marketType === 'US' ? 4 : 4;
          
          // 添加币种符号
          const price = `${marketInfo.currency}${values[priceIndex]}`;
          const prevClose = `${marketInfo.currency}${values[prevCloseIndex]}`;
          
          tableData.push([
            `${stockName}(${marketInfo.name})`,
            stockCode,
            price,
            values[changeIndex] + '%',
            prevClose
          ]);

          // 如果开启了日K或周K选项，获取并打印K线图表
          if (options.day) {
            const dayKData = await getKLineData(stockCode, 'day');
            printKLineChart(dayKData, '日', stockName, stockCode);
          }
          if (options.week) {
            const weekKData = await getKLineData(stockCode, 'week');
            printKLineChart(weekKData, '周', stockName, stockCode);
          }
        }
      }
    }

    console.log('\n实时行情:');
    console.log(table(tableData));
  } catch (error) {
    console.error('获取数据失败:', error.message);
  }
}