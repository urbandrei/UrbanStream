const COLS=4,ROWS=7,DISPLAY=77,SPEED=80;
const WALK=[{c:0,r:1},{c:1,r:1},{c:2,r:1},{c:3,r:1}];
let DW=DISPLAY,DH=DISPLAY;
const known={};
const jailed=new Set();
let jailEl=null,jailInmates=null,jailCage=null;
function rand(a,b){return Math.random()*(b-a)+a}

function wrapText(s){
  const MAX_LINE=50,MAX_LINES=3;
  const lines=[];let rem=s;
  while(rem.length>0&&lines.length<MAX_LINES){
    if(rem.length<=MAX_LINE){lines.push(rem);break}
    let cut=MAX_LINE;
    const brk=rem.lastIndexOf(' ',MAX_LINE);
    const pb=rem.search(/[.,!?;:]\s/);
    if(pb>0&&pb<=MAX_LINE)cut=pb+1;
    else if(brk>0)cut=brk;
    lines.push(rem.slice(0,cut).trimEnd());
    rem=rem.slice(cut).trimStart();
  }
  if(rem.length>0&&lines.length===MAX_LINES){
    const last=lines[MAX_LINES-1];
    if(last.length>MAX_LINE-3)lines[MAX_LINES-1]=last.slice(0,MAX_LINE-3)+'...';
    else lines[MAX_LINES-1]=last+'...';
  }
  return lines.join('\n');
}

function setFrame(spr,col,row,flip){
  spr.style.backgroundPosition=(-col*DW)+'px '+(-row*DH)+'px';
  spr.style.transform=flip?'scaleX(-1)':'';
}

function createJailDOM(){
  jailEl=document.createElement('div');
  jailEl.id='jail';

  jailCage=document.createElement('div');
  jailCage.id='jail-cage';

  const ceiling=document.createElement('div');
  ceiling.id='jail-ceiling';

  jailInmates=document.createElement('div');
  jailInmates.id='jail-inmates';

  const barsContainer=document.createElement('div');
  barsContainer.id='jail-bars';
  for(let i=0;i<8;i++){
    const bar=document.createElement('div');
    bar.className='bar';
    barsContainer.appendChild(bar);
  }

  const floor=document.createElement('div');
  floor.id='jail-floor';

  jailCage.appendChild(ceiling);
  jailCage.appendChild(jailInmates);
  jailCage.appendChild(barsContainer);
  jailCage.appendChild(floor);

  jailEl.appendChild(jailCage);
  document.body.appendChild(jailEl);
}

function arrangeInmates(){
  const count=jailed.size;
  if(count===0){
    jailEl.classList.remove('active');
    return;
  }
  jailEl.classList.add('active');
  // Resize cage to fit inmates (min 300px, ~DW+24 per inmate)
  const needed=count*(DW+24)+24;
  jailCage.style.width=Math.max(300,needed)+'px';
}

function jailUser(name){
  const info=known[name];
  if(!info||jailed.has(name))return;
  jailed.add(name);

  // Stop all movement
  clearInterval(info.ai);
  clearTimeout(info.st);
  clearTimeout(info.mt);
  setFrame(info.spr,0,0,false);

  // Move element into jail cage
  info.el.classList.add('jailed');
  info.el.style.transitionDuration='0s';
  info.el.style.transform='none';
  jailInmates.appendChild(info.el);

  arrangeInmates();
}

function unjailUser(name){
  const info=known[name];
  if(!info||!jailed.has(name))return;
  jailed.delete(name);

  // Play fall animation
  info.el.style.animation='jail-fall 0.8s ease-in forwards';

  setTimeout(()=>{
    info.el.style.animation='';
    info.el.classList.remove('jailed');

    // Return to ground
    document.body.appendChild(info.el);
    const maxX=Math.max(0,window.innerWidth-DW);
    const sx=rand(0,maxX);
    info.x=sx;
    info.el.style.transitionDuration='0s';
    info.el.style.transform='translateX('+sx+'px)';
    setFrame(info.spr,0,0,false);

    // Resume walking
    info.mt=setTimeout(()=>moveTo(info),rand(1000,4000));
  },800);

  arrangeInmates();
}

function moveInJail(info){
  // Constrained movement within jail cage
  if(!jailInmates)return;
  const cageW=jailCage.offsetWidth-24;
  const maxX=Math.max(0,cageW-DW);
  const newX=Math.min(maxX,Math.max(0,rand(0,maxX)));
  const goLeft=newX<info.x;
  info.x=newX;
  info.fi=0;
  clearInterval(info.ai);
  info.ai=setInterval(()=>{
    const f=WALK[info.fi%WALK.length];
    setFrame(info.spr,f.c,f.r,goLeft);
    info.fi++;
  },200); // slower walk in jail
  clearTimeout(info.st);
  info.st=setTimeout(()=>{
    clearInterval(info.ai);
    setFrame(info.spr,0,0,false);
    if(jailed.has(Object.keys(known).find(k=>known[k]===info)||'')){
      info.mt=setTimeout(()=>moveInJail(info),rand(3000,8000));
    }
  },1500);
}

function moveTo(info){
  // If jailed, use constrained movement instead
  if(jailed.has(Object.keys(known).find(k=>known[k]===info)||'')){
    moveInJail(info);
    return;
  }
  const maxX=Math.max(0,window.innerWidth-DW);
  const newX=Math.min(maxX,Math.max(0,rand(0,maxX)));
  const dist=Math.abs(newX-info.x);
  const dur=Math.max(0.5,dist/SPEED);
  const goLeft=newX<info.x;
  info.x=newX;
  info.fi=0;
  clearInterval(info.ai);
  info.ai=setInterval(()=>{
    const f=WALK[info.fi%WALK.length];
    setFrame(info.spr,f.c,f.r,goLeft);
    info.fi++;
  },150);
  info.el.style.transitionDuration=dur+'s';
  info.el.style.transform='translateX('+newX+'px)';
  clearTimeout(info.st);
  info.st=setTimeout(()=>{
    clearInterval(info.ai);
    setFrame(info.spr,0,0,false);
    info.mt=setTimeout(()=>moveTo(info),rand(3000,8000));
  },dur*1000);
}

function addChatter(name){
  if(known[name])return;
  const div=document.createElement('div');
  div.className='chatter';
  const bub=document.createElement('div');
  bub.className='bubble';
  const lbl=document.createElement('div');
  lbl.className='name';lbl.textContent=name;
  const spr=document.createElement('div');
  spr.className='sprite';
  spr.style.width=DW+'px';spr.style.height=DH+'px';
  spr.style.backgroundSize=(COLS*DW)+'px '+(ROWS*DH)+'px';
  div.appendChild(bub);div.appendChild(lbl);div.appendChild(spr);
  div.style.transitionDuration='0s';
  document.body.appendChild(div);
  const maxX=Math.max(0,window.innerWidth-DW);
  const sx=rand(0,maxX);
  div.style.transform='translateX('+sx+'px)';
  const info={el:div,spr:spr,bub:bub,x:sx,fi:0,ai:null,st:null,mt:null};
  known[name]=info;
  setFrame(spr,0,0,false);
  info.mt=setTimeout(()=>moveTo(info),rand(1000,4000));
}

function removeChatter(name){
  if(!known[name])return;
  const i=known[name];
  clearInterval(i.ai);clearTimeout(i.st);clearTimeout(i.mt);
  i.el.remove();delete known[name];
  jailed.delete(name);
  arrangeInmates();
}

async function poll(){
  try{
    const r=await fetch('/api/chatters');
    const data=await r.json();
    const cur=new Set(Object.keys(data));
    for(const n of Object.keys(known)){if(!cur.has(n))removeChatter(n)}
    for(const n of Object.keys(data)){
      addChatter(n);
      if(known[n]){
        // Handle jail state transitions
        const shouldBeJailed=!!data[n].jailed;
        const isJailed=jailed.has(n);
        if(shouldBeJailed&&!isJailed)jailUser(n);
        else if(!shouldBeJailed&&isJailed)unjailUser(n);

        if(data[n].msg){known[n].bub.textContent=wrapText(data[n].msg);known[n].bub.style.display='block'}
        else{known[n].bub.style.display='none'}
      }
    }
  }catch(e){}
}

const img=new Image();img.src='/bot.png';
img.onload=()=>{
  const fw=img.width/COLS,fh=img.height/ROWS;
  DH=DISPLAY;DW=Math.round(DISPLAY*(fw/fh));
  createJailDOM();
  setInterval(poll,1000);poll();
};
